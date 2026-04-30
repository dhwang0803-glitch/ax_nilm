import type {
  AccountResponse,
  NotificationsResponse,
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
