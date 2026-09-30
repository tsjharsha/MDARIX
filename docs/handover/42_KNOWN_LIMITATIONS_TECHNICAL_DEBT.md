# Known Limitations and Technical Debt

- Some legacy business routes still require incremental migration to the data-plane dependency.
- Full route-by-route isolation coverage must include every legacy search, export, attachment, report, AI and worker endpoint.
- Some frontend screens still use generic record tables instead of domain-specific cards.
- `frontend/src/main.tsx` remains larger than the preferred modular boundary.
- Browser screenshots, screen-reader review and full authenticated mobile evidence require browser execution.
- Production PostgreSQL TLS, runtime least-privilege cutover, encrypted backups/PITR, monitoring and hosted multi-instance validation are not local MVP evidence.
- Real customer endpoint/schema/credential validation is not represented by simulators.
- Regulatory document generation must not be described as a certified submission package.
