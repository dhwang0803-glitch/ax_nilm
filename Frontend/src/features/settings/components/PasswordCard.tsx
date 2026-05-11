import { useState, type FormEvent } from "react";

type FormState = { current: string; next: string; confirm: string };

const EMPTY: FormState = { current: "", next: "", confirm: "" };

export function PasswordCard() {
  const [form, setForm] = useState<FormState>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    if (!form.current || !form.next || !form.confirm) {
      setError("모든 항목을 입력해주세요.");
      return;
    }
    if (form.next !== form.confirm) {
      setError("신규 비밀번호와 확인이 일치하지 않습니다.");
      return;
    }

    setSubmitting(true);
    setTimeout(() => {
      setSuccess("비밀번호가 변경되었습니다. (mock)");
      setForm(EMPTY);
      setSubmitting(false);
    }, 200);
  };

  const update = (key: keyof FormState) => (v: string) =>
    setForm((prev) => ({ ...prev, [key]: v }));

  return (
    <section
      className="border border-line-2 bg-canvas p-6"
      aria-labelledby="password-card-heading"
    >
      <header>
        <h3
          id="password-card-heading"
          className="text-base font-semibold text-ink-1"
        >
          비밀번호 변경
        </h3>
      </header>
      <form onSubmit={handleSubmit} className="mt-4 flex flex-col gap-3 text-sm">
        <Field
          id="pw-current"
          label="현재 비밀번호"
          value={form.current}
          onChange={update("current")}
        />
        <Field
          id="pw-next"
          label="신규 비밀번호"
          value={form.next}
          onChange={update("next")}
        />
        <Field
          id="pw-confirm"
          label="신규 비밀번호 확인"
          value={form.confirm}
          onChange={update("confirm")}
        />
        {error && (
          <p role="alert" className="text-xs text-red-600">
            {error}
          </p>
        )}
        {success && (
          <p role="status" className="text-xs text-emerald-600">
            {success}
          </p>
        )}
        <div>
          <button
            type="submit"
            disabled={submitting}
            className="border border-ink-1 bg-ink-1 px-3 py-1.5 text-xs text-canvas disabled:opacity-50"
          >
            {submitting ? "변경 중…" : "변경"}
          </button>
        </div>
      </form>
    </section>
  );
}

function Field({
  id,
  label,
  value,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="grid grid-cols-[140px_1fr] items-center gap-3">
      <label htmlFor={id} className="text-ink-3">
        {label}
      </label>
      <input
        id={id}
        type="password"
        autoComplete="new-password"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="border border-line-2 bg-canvas px-2 py-1.5 text-sm"
      />
    </div>
  );
}
