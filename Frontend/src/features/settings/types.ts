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
