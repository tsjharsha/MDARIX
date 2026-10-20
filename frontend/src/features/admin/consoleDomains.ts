import { Database, LayoutDashboard, LifeBuoy, LockKeyhole, Settings2, ShieldCheck, Users } from "lucide-react";
import { SECTIONS as CUSTOMER_TENANT_SECTIONS } from "./customers/model";
import {
  AI_SECTIONS,
  DATA_INTEGRATION_SECTIONS,
  IDENTITY_SECTIONS,
  OPERATIONS_SECTIONS,
  PLANS_SECTIONS,
  SECURITY_SECTIONS,
} from "./areas/sections";

/** The platform administration console's areas: name, one-line purpose, icon and sections, in menu order. */
export const DOMAINS = [
  ["Platform Overview", "Health, activity and attention", LayoutDashboard, ["Overview"]],
  ["Customers & Tenants", "Customer and tenant lifecycle", Users, CUSTOMER_TENANT_SECTIONS],
  ["Plans & Licensing", "Plans, subscriptions and reminders", Settings2, PLANS_SECTIONS],
  ["Identity & Access", "Accounts, roles and onboarding requests", LockKeyhole, IDENTITY_SECTIONS],
  ["Data & Integrations", "Define, connect, map, release and run customer data", Database, DATA_INTEGRATION_SECTIONS],
  ["AI Control Center", "Models, evaluations and assurance", ShieldCheck, AI_SECTIONS],
  ["Security", "Isolation, audit, support access and retention", LockKeyhole, SECURITY_SECTIONS],
  ["Operations", "Health, queues, email, problem reports and API", LifeBuoy, OPERATIONS_SECTIONS],
] as const;
