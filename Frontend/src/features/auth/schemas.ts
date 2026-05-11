import { z } from "zod";

export const loginSchema = z.object({
  email: z.string().email("올바른 이메일 형식이 아닙니다"),
  password: z.string().min(8, "비밀번호는 8자 이상이어야 합니다"),
  rememberMe: z.boolean().optional(),
});

export type LoginFormData = z.infer<typeof loginSchema>;

const KEPCO_PATTERN = /^\d{10}$/;

export const signupSchema = z
  .object({
    email: z.string().email("올바른 이메일 형식이 아닙니다"),
    password: z.string().min(8, "비밀번호는 8자 이상이어야 합니다"),
    passwordConfirm: z.string().min(1, "비밀번호 확인을 입력해주세요"),
    name: z.string().min(1, "이름을 입력해주세요"),
    skipKepco: z.boolean(),
    kepcoCustomerNumber: z.string().optional(),
    agreeTerms: z.literal(true, { message: "약관에 동의해주세요" }),
  })
  .refine((data) => data.password === data.passwordConfirm, {
    path: ["passwordConfirm"],
    message: "비밀번호가 일치하지 않습니다",
  })
  .refine(
    (data) => data.skipKepco || KEPCO_PATTERN.test(data.kepcoCustomerNumber ?? ""),
    {
      path: ["kepcoCustomerNumber"],
      message: "한전 고객번호는 10자리 숫자여야 합니다",
    }
  );

export type SignupFormData = z.infer<typeof signupSchema>;
