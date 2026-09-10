from uuid import UUID

from cce.context_packages.models.assets import Evidence, GovernedAsset, PackageSnapshot


class ContextRepository:
    def __init__(self, db):
        self.db = db

    def active(self, workspace_uuid: UUID, cur=None) -> PackageSnapshot | None:
        if cur is None:
            with self.db.transaction() as cursor:
                return self.active(workspace_uuid, cursor)
        cur.execute(
            """SELECT p.package_id,p.workspace_uuid,v.package_version_id,v.version_no,v.status
            FROM context_package p JOIN package_version v USING(package_id)
            WHERE p.workspace_uuid=%s AND v.status='ACTIVE'""", (str(workspace_uuid),))
        row=cur.fetchone()
        return self._manifest(cur,row) if row else None

    def _manifest(self,cur,row):
        # Relational manifest and immutable revisions are authoritative; JSON is derived.
        cur.execute("""SELECT a.asset_id,r.asset_revision_id,a.workspace_uuid,r.revision_no,r.payload,p.resolved_by approved_by
            FROM package_asset pa JOIN context_asset_revision r USING(asset_revision_id)
            JOIN context_asset a USING(asset_id) JOIN proposal p ON p.proposal_id=r.created_from_proposal_id
            WHERE pa.package_version_id=%s ORDER BY a.asset_type,a.canonical_key""", (str(row['package_version_id']),))
        assets=[GovernedAsset.model_validate(dict(record)) for record in cur.fetchall()]
        package=PackageSnapshot(package_id=row['package_id'],workspace_uuid=row['workspace_uuid'],package_version_id=row['package_version_id'],
            version=row['version_no'],status=row['status'],assets=assets)
        return self._hydrate(package,cur)

    def _hydrate(self, package, cur):
        # Evidence support can grow without changing an immutable semantic revision.
        cur.execute(
            "SELECT ae.asset_revision_id::text,e.* FROM package_asset pa JOIN asset_revision_evidence ae USING(asset_revision_id)\n            JOIN context_evidence e USING(evidence_id) WHERE pa.package_version_id=%s",
            (str(package.package_version_id),),
        )
        refs = {}
        for row in cur.fetchall():
            record = dict(row)
            revision = record.pop("asset_revision_id")
            refs.setdefault(revision, []).append(Evidence.model_validate(record))
        return package.model_copy(
            update={
                "assets": [
                    a.model_copy(
                        update={"evidence": refs.get(str(a.asset_revision_id), [])}
                    )
                    for a in package.assets
                ]
            }
        )

    def get_package(self, workspace_uuid):
        with self.db.transaction() as cur:
            cur.execute("SELECT p.package_id,p.workspace_uuid,p.name,(SELECT version_no FROM package_version v WHERE v.package_id=p.package_id AND status='ACTIVE') active_version FROM context_package p WHERE workspace_uuid=%s",(str(workspace_uuid),))
            row=cur.fetchone()
            if not row: raise KeyError('Workspace package not found')
            return dict(row)

    def rename(self, workspace_uuid, name):
        if not name.strip(): raise ValueError('Package name is required')
        with self.db.transaction() as cur:
            cur.execute('UPDATE context_package SET name=%s WHERE workspace_uuid=%s RETURNING package_id',(name,str(workspace_uuid)))
            if not cur.fetchone(): raise KeyError('Workspace package not found')
        return self.get_package(workspace_uuid)

    def versions(self, workspace_uuid):
        with self.db.transaction() as cur:
            cur.execute('SELECT v.version_no version,v.status,v.created_at FROM package_version v JOIN context_package p USING(package_id) WHERE p.workspace_uuid=%s ORDER BY v.version_no DESC',(str(workspace_uuid),))
            return [dict(row) for row in cur.fetchall()]

    def version(self, workspace_uuid, version):
        with self.db.transaction() as cur:
            cur.execute("SELECT p.package_id,p.workspace_uuid,v.package_version_id,v.version_no,v.status FROM context_package p JOIN package_version v USING(package_id) WHERE p.workspace_uuid=%s AND v.version_no=%s",(str(workspace_uuid),int(version)))
            row=cur.fetchone()
            if not row: raise KeyError('Workspace package version not found')
            return self._manifest(cur,row)

    def linked_assets(
        self, package: PackageSnapshot, memory_ids: list[str]
    ) -> list[GovernedAsset]:
        if not memory_ids:
            return []
        with self.db.transaction() as cur:
            cur.execute(
                """SELECT DISTINCT pa.asset_revision_id::text FROM package_asset pa
                JOIN asset_revision_evidence ae USING(asset_revision_id) JOIN context_evidence e USING(evidence_id)
                WHERE pa.package_version_id=%s AND e.agentic_memory_id=ANY(%s)""",
                (str(package.package_version_id), memory_ids),
            )
            ids = {r["asset_revision_id"] for r in cur.fetchall()}
            package = self._hydrate(package, cur)
        return [a for a in package.assets if str(a.asset_revision_id) in ids]

    def expand(
        self, package: PackageSnapshot, seeds: list[GovernedAsset], hops: int
    ) -> list[GovernedAsset]:
        with self.db.transaction() as cur:
            package = self._hydrate(package, cur)
        selected = {str(a.asset_revision_id) for a in seeds}
        keys = {a.payload.canonical_key for a in seeds}
        for asset in seeds:
            keys.update(asset.payload.dependencies)
            keys.update(getattr(asset.payload, "entity_keys", []))
        with self.db.transaction() as cur:
            cur.execute(
                """SELECT e.entity_id::text,e.canonical_key,e.asset_revision_id::text FROM graph_entity e
                JOIN package_asset pa USING(asset_revision_id) WHERE pa.package_version_id=%s""",
                (str(package.package_version_id),),
            )
            entities = {r["entity_id"]: dict(r) for r in cur.fetchall()}
            cur.execute(
                """SELECT e.from_entity_id::text,e.to_entity_id::text,e.asset_revision_id::text FROM graph_edge e
                JOIN package_asset pa USING(asset_revision_id) WHERE pa.package_version_id=%s""",
                (str(package.package_version_id),),
            )
            edges = [
                dict(r)
                for r in cur.fetchall()
                if r["from_entity_id"] in entities and r["to_entity_id"] in entities
            ]
        visited = {i for i, e in entities.items() if e["canonical_key"] in keys}
        frontier = set(visited)
        for _ in range(hops):
            following = set()
            for e in edges:
                if e["from_entity_id"] in frontier or e["to_entity_id"] in frontier:
                    selected.add(e["asset_revision_id"])
                    following.update((e["from_entity_id"], e["to_entity_id"]))
            following &= entities.keys()
            frontier = following - visited
            visited |= following
        selected.update(entities[i]["asset_revision_id"] for i in visited)
        # Explicit dependencies are structural references, not additional graph hops.
        while True:
            dependencies = {
                k
                for a in package.assets
                if str(a.asset_revision_id) in selected
                for k in a.payload.dependencies
            }
            extra = {
                str(a.asset_revision_id)
                for a in package.assets
                if a.payload.canonical_key in dependencies
            }
            if extra <= selected:
                break
            selected |= extra
        return [a for a in package.assets if str(a.asset_revision_id) in selected]
