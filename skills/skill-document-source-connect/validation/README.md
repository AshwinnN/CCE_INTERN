# Validation - Document Source Connect

Thirteen cases covering all ten Core Rules. Mirrors the structured connect suite.

- **Adapter agnosticism** - TC-001 to TC-004 connect Drive, Gmail, SharePoint and
  Slack through one path and produce an identical handle shape. TC-013 adds a
  fifth, local-fs, proven with a real write-probe and os.stat() rather than
  fixture booleans.
- **Two boundaries, not one** - TC-007 and TC-011 cover read-only proof; TC-012
  covers entitlement capture. The second is what makes this skill differ from
  its structured sibling: `public-bucket` can prove it is read-only but cannot
  read per-object ACLs, so it is registrable and never connectable. Without that
  refusal the corpus answers every user from the union of all documents.
- **Profile hygiene** - inline credentials, missing limits, fallback sources and
  document listings are each refused.
