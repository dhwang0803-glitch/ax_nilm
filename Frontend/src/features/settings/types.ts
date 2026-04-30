export type AccountProfile = {
  name: string;
  email: string;
  phone: string;
  memberCount: number;
};

export type AccountKepco = {
  customerNo: string;
  addressMasked: string;
  contractType: string;
  linkedAt: string;
};

export type AccountResponse = {
  profile: AccountProfile;
  kepco: AccountKepco;
};

export type NotificationKind =
  | "anomaly"
  | "cashback"
  | "weeklyReport"
  | "system";

export type NotificationMatrixRow = {
  kind: NotificationKind;
  email: boolean;
  sms: boolean;
  push: boolean;
};

export type DoNotDisturb = {
  enabled: boolean;
  startMinutes: number;
  endMinutes: number;
};

export type NotificationsResponse = {
  matrix: NotificationMatrixRow[];
  doNotDisturb: DoNotDisturb;
};

export type SecuritySession = {
  id: string;
  device: string;
  location: string;
  lastActiveAt: string;
  current: boolean;
};

export type SecurityResponse = {
  twoFactorEnabled: boolean;
  sessions: SecuritySession[];
};

export type AnomalySeverity = "low" | "medium" | "high";
export type AnomalyStatus = "open" | "resolved";

export type AnomalyEvent = {
  id: string;
  occurredAt: string;
  appliance: string;
  severity: AnomalySeverity;
  description: string;
  status: AnomalyStatus;
};

export type AnomalyEventsResponse = {
  kpi: {
    monthCount: number;
    avgResponseMinutes: number;
    unresolvedCount: number;
  };
  events: AnomalyEvent[];
};
