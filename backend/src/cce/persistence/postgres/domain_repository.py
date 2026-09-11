from cce.governance.models import Actor, Domain, DomainCreate
from cce.persistence.postgres.lifecycle_db import json_param


class DomainRepository:
    def __init__(self, db):
        self.db = db

    def create(self, request: DomainCreate, actor: Actor) -> Domain:
        actor.require("ADMIN")
        domain = Domain(**request.model_dump())
        with self.db.transaction() as cur:
            cur.execute(
                "INSERT INTO domain(domain_id,name,description,tags,metadata) VALUES(%s,%s,%s,%s,%s)",
                (
                    str(domain.domain_id),
                    domain.name,
                    domain.description,
                    json_param(domain.tags),
                    json_param(domain.metadata),
                ),
            )
        return domain

    def list(self) -> list[Domain]:
        with self.db.transaction() as cur:
            cur.execute("""SELECT d.domain_id::text,d.name,d.description,d.tags,d.metadata,d.enabled,
                EXISTS(SELECT 1 FROM context_package p JOIN package_version v USING(package_id)
                WHERE p.domain_id=d.domain_id AND v.status='ACTIVE') has_active_package
                FROM domain d WHERE enabled ORDER BY name""")
            return [Domain.model_validate(dict(r)) for r in cur.fetchall()]
