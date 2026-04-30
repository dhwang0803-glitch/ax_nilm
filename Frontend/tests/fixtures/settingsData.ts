import type {
  AccountResponse,
  AnomalyEventsResponse,
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

export const mockAnomalyEvents: AnomalyEventsResponse = {
  kpi: {
    monthCount: 8,
    avgResponseMinutes: 192,
    unresolvedCount: 2,
  },
  events: [
    {
      id: "ev-001",
      occurredAt: "2026-04-29 14:22",
      appliance: "에어컨",
      severity: "high",
      description: "정격 대비 25% 과소비 (필터 점검 권장)",
      status: "open",
    },
    {
      id: "ev-002",
      occurredAt: "2026-04-28 09:11",
      appliance: "김치냉장고",
      severity: "medium",
      description: "평소 대비 12% 추가 소비 감지",
      status: "open",
    },
    {
      id: "ev-003",
      occurredAt: "2026-04-26 19:45",
      appliance: "세탁기",
      severity: "low",
      description: "표준 코스 대비 15분 지연",
      status: "resolved",
    },
    {
      id: "ev-004",
      occurredAt: "2026-04-24 11:03",
      appliance: "건조기",
      severity: "medium",
      description: "정상 대비 18% 과소비 (필터 청소 후 정상)",
      status: "resolved",
    },
    {
      id: "ev-005",
      occurredAt: "2026-04-22 22:48",
      appliance: "인덕션",
      severity: "low",
      description: "대기 전력 평소 대비 5W 증가",
      status: "resolved",
    },
    {
      id: "ev-006",
      occurredAt: "2026-04-19 06:15",
      appliance: "에어컨",
      severity: "high",
      description: "정상 가동 후 자동 정지 반복",
      status: "resolved",
    },
    {
      id: "ev-007",
      occurredAt: "2026-04-15 13:30",
      appliance: "TV",
      severity: "low",
      description: "대기 전력 0.4W 초과",
      status: "resolved",
    },
    {
      id: "ev-008",
      occurredAt: "2026-04-12 20:02",
      appliance: "세탁기",
      severity: "medium",
      description: "탈수 시 모터 부하 증가",
      status: "resolved",
    },
  ],
};
