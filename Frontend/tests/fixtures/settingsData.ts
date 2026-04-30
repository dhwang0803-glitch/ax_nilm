import type {
  AccountResponse,
  NotificationsResponse,
  SecurityResponse,
} from "../../src/features/settings/types";

export const mockAccount: AccountResponse = {
  profile: {
    name: "테스터",
    email: "test@example.com",
    phone: "010-****-1234",
    memberCount: 3,
  },
  kepco: {
    customerNo: "12-3456-7890-12",
    addressMasked: "서울특별시 ○○구 ○○로 ***",
    contractType: "주택용 저압",
    linkedAt: "2026-04-15",
  },
};

export const mockNotifications: NotificationsResponse = {
  matrix: [
    { kind: "anomaly", email: true, sms: true, push: true },
    { kind: "cashback", email: true, sms: false, push: true },
    { kind: "weeklyReport", email: true, sms: false, push: false },
    { kind: "system", email: false, sms: false, push: true },
  ],
  doNotDisturb: {
    enabled: true,
    startMinutes: 22 * 60,
    endMinutes: 7 * 60,
  },
};

export const mockSecurity: SecurityResponse = {
  twoFactorEnabled: false,
  sessions: [
    {
      id: "s-cur",
      device: "Chrome · macOS",
      location: "서울",
      lastActiveAt: "2026-04-30 09:42",
      current: true,
    },
    {
      id: "s-mob",
      device: "Safari · iPhone 15",
      location: "서울",
      lastActiveAt: "2026-04-29 21:18",
      current: false,
    },
    {
      id: "s-other",
      device: "Edge · Windows 11",
      location: "부산",
      lastActiveAt: "2026-04-26 14:03",
      current: false,
    },
  ],
};
