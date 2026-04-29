import type { AccountResponse } from "../../src/features/settings/types";

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
