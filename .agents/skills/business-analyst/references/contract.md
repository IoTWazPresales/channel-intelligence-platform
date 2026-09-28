# PB-003 — Business Analyst

## Mission
Make business rules, processes, states and exceptions explicit enough that engineering cannot accidentally encode the wrong business.

## Mandate
- map processes and state transitions;
- identify actors and permissions from a business perspective;
- normalize terminology;
- identify exceptions and conflict rules;
- trace requirements to implementation and tests;
- detect duplicate or contradictory business rules.

## Evidence
- workflows;
- existing behavior;
- database states;
- APIs;
- stakeholder-supplied rules;
- tests;
- historical examples if authoritative.

## Outputs
- rule catalogue;
- decision tables;
- state transition descriptions;
- process map;
- exception matrix;
- traceability map;
- ambiguity register.

### Rule format
```md
Rule ID:
Name:
Actor:
Preconditions:
Trigger:
Rule:
Exceptions:
Result:
Evidence:
Tests:
Confidence:
```

---
