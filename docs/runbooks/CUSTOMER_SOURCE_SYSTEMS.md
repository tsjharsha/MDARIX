# Simulated customer systems: load a tenant's data and connect MDARIX

MDARIX reads a customer's data from the systems the customer already runs. For testing without a real customer, 11
simulated systems stand in for them. Each is a small API with its own database server:

| System | Port | Simulates |
|---|---:|---|
| `TRACKWISE` | 8101 | TrackWise Digital (complaints, investigations, CAPAs) |
| `PLM`, `ERP`, `SUPPLIER` | 8102–8104 | Original synthetic simulators (still used by older tests) |
| `VEEVA_QMS` | 8105 | Veeva Vault QMS (quality events, CAPAs, documents) |
| `TEAMCENTER` | 8106 | Siemens Teamcenter (items, revisions, BOM, changes, requirements) |
| `ORACLE_ERP` | 8107 | Oracle Fusion (items, sites, lots, suppliers, approved suppliers) |
| `COUPA` | 8108 | Coupa (suppliers, supplier risk, certificates) |
| `SAP_ERP` | 8109 | SAP S/4HANA (materials, plants, batches, batch where-used, vendors, source list) |
| `WINDCHILL` | 8110 | PTC Windchill (parts, versions, BOM, change notices) |
| `MES` | 8111 | Manufacturing execution (production orders, genealogy) |
| `LIMS` | 8112 | Laboratory system (test results) |
| `RISK` | 8113 | Risk management file (risks, FMEA, risk controls) |
| `SALESFORCE_SERVICE` | 8114 | Salesforce Service (service cases) |

**Each tenant has its own database and API key in every system**, the way each customer runs its own TrackWise or
SAP. A key reads only its tenant's records. The CSV layout of every record is in `data/source-templates/`
(see its README and `_data_dictionary.csv`).

## 1. One-time setup

1. In `.env`, set:
   - `MDARIX_SIMULATOR_ADMIN_TOKEN`: a long random value. It lets you create tenants in the simulators; without it,
     the admin API answers 503.
   - `MDARIX_CONNECTOR_ALLOWED_HOSTS`: include `127.0.0.1:8101` to `127.0.0.1:8114`, so MDARIX may call the
     simulators.
   - `MDARIX_CONNECTOR_ENCRYPTION_KEY`: URL-safe base64 of 32 random bytes. It encrypts the API keys MDARIX
     stores. Development has a built-in key; every other environment needs this setting.
2. Start or rebuild the simulators: `docker compose up -d --build` (the new ones share the `source-systems-db`
   server).

## 2. Load a tenant's data into the simulated systems

```text
python scripts/load_source_templates.py --tenant ACME_MEDICAL --keys C:/Users/<you>/acme-source-keys.json
```

- Without `--data`, it loads the example story from the templates. To load your own data, put your CSV files in a
  folder with the same layout (`SAP_ERP/batches.csv`, `TRACKWISE/complaints.csv`, ...) and pass `--data <folder>`.
- Each file is checked first: unknown or missing columns, an empty required value, or a repeated key rejects the
  whole file, with the row and reason.
- The API keys are written to the `--keys` file. Keep it private: anyone with a key can read that tenant's records.
- You can also upload one file at a time in a browser: open `http://127.0.0.1:<port>/`, paste the key, choose the
  record type and the file.

## 3. Connect MDARIX (Customer Admin → Integrations)

For each record type, do these steps once:

1. **Data Mapping → New mapping.** Choose the system and the record, then **Use the standard mapping**. For records
   that mix kinds, such as Teamcenter items, SAP materials, Oracle items and Windchill parts, there is one standard
   mapping per kind: products and components. Check it, save it, request approval; a second administrator approves
   and releases it.
2. **Integrations → Add a connection:**
   - Endpoint: `http://127.0.0.1:<port>`
   - Record to read: the record name, e.g. `complaints`
   - Mapping: the released mapping
3. **Set API key** on the connection: paste the key from your keys file. MDARIX encrypts it; it is never shown
   again.
4. **Health**, then activate the connection, then **Sync now**. The result says what was imported, updated, left out
   by the mapping's filter, or refused and why.

### Load order

A record that refers to another needs that one first. Sync in this order:

1. suppliers and sites
2. products (and versions)
3. components
4. bills of materials
5. approved suppliers
6. lots
7. lot genealogy
8. risks
9. failure modes, controls, requirements
10. complaints
11. investigations
12. CAPAs
13. changes
14. evidence (documents, test results, certificates, service cases)

`backend/app/access/standard_mappings.json` lists the standard mappings in this order.

## What MDARIX does with the records

- Every record goes through the checked import: references must resolve inside the tenant, personal data is
  refused, and a batch with any problem writes nothing.
- Complaints, investigations, CAPAs, changes, requirements, risks, failure modes and controls also become searchable
  evidence. Ask MDARIX and the investigator find them at once by product, version, lot or record. Semantic search
  embeddings are added in the background after each sync.
