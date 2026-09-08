from uuid import UUID

from cce.context_packages.models.assets import Evidence, GovernedAsset, PackageSnapshot


class ContextRepository:
    def __init__(self, db):
        self.db = db

    def active(self, domain_id: UUID, cur=None) -> PackageSnapshot | None:
        if cur is None:
            with self.db.transaction() as cursor:
                return self.active(domain_id, cursor)
        cur.execute(
            """SELECT p.package_id,p.domain_id,v.package_version_id,v.version_no,v.status
            FROM context_package p JOIN package_version v USING(package_id)
            WHERE p.domain_id=%s AND v.status='ACTIVE'""", (str(domain_id),))
        row=cur.fetchone()
        return self._manifest(cur,row) if row else None

    def _manifest(self,cur,row):
        # Relational manifest and immutable revisions are authoritative; JSON is derived.
        cur.execute("""SELECT a.asset_id,r.asset_revision_id,a.domain_id,r.revision_no,r.payload,p.resolved_by approved_by
            FROM package_asset pa JOIN context_asset_revision r USING(asset_revision_id)
            JOIN context_asset a USING(asset_id) JOIN proposal p ON p.proposal_id=r.created_from_proposal_id
            WHERE pa.package_version_id=%s ORDER BY a.asset_type,a.canonical_key""", (str(row['package_version_id']),))
        assets=[GovernedAsset.model_validate(dict(record)) for record in cur.fetchall()]
        package=PackageSnapshot(package_id=row['package_id'],domain_id=row['domain_id'],package_version_id=row['package_version_id'],
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

    def list_packages(self):
        with self.db.transaction() as cur:
            cur.execute(
                "SELECT package_id::text,domain_id::text,name FROM context_package ORDER BY name"
            )
            return [dict(r) for r in cur.fetchall()]

    def get_package(self, package_id):
        with self.db.transaction() as cur:
            cur.execute(
                "SELECT package_id::text,domain_id::text,name FROM context_package WHERE package_id=%s",
                (str(package_id),),
            )
            row = cur.fetchone()
            if not row:
                raise KeyError("Package not found")
            return dict(row)

    def version(self, package_id, version) -> PackageSnapshot:
        with self.db.transaction() as cur:
            cur.execute("""SELECT p.package_id,p.domain_id,v.package_version_id,v.version_no,v.status
                FROM context_package p JOIN package_version v USING(package_id)
                WHERE p.package_id=%s AND v.version_no=%s""",(str(package_id),int(str(version).lstrip('v'))))
            row=cur.fetchone()
            if not row:raise KeyError('Package version not found')
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
