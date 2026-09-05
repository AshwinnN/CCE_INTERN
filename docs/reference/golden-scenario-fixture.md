# Golden Scenario Fixture Proposal

Status: proposed for team sign-off; not authoritative yet.

## Structured Fixture

Use the Snowflake schema already configured for the live connector tests.

Object: `delivery_performance`

Columns:

- `customer_name` STRING
- `measurement_period` DATE
- `total_deliveries` NUMBER
- `on_time_deliveries` NUMBER
- `on_time_rate` NUMBER(5,2)

Rows:

| customer_name | measurement_period | total_deliveries | on_time_deliveries | on_time_rate |
| --- | --- | ---: | ---: | ---: |
| Customer ABC | 2026-09-01 | 100 | 82 | 0.82 |

## Unstructured Fixture

Contract document:

```text
Customer ABC Delivery SLA Override

For Customer ABC, the approved delivery SLA threshold is 80% on-time delivery.
This override is valid until 2026-09-30.
```

Policy document:

```text
Global Delivery SLA Policy

Unless an approved customer-specific override exists, the default delivery SLA
threshold is 90% on-time delivery.
```

## Expected Answers

Context OFF:

```text
Customer ABC has an 82% on-time delivery rate. Compared with the 90% global
default SLA, Customer ABC does not meet the SLA.
```

Context ON:

```text
Customer ABC has an 82% on-time delivery rate. Compared with the approved 80%
Customer ABC override valid until 2026-09-30, Customer ABC meets the SLA.
```
