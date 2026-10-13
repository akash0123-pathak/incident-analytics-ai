import { useEffect, useState } from "react";
import { IconAlertTriangle, IconCheckCircle, IconX } from "./Icons.jsx";

const DEMO_PINS = {
  manager: "4567",
  executive: "8910",
};

export default function RolePinModal({ role, roleLabel, onSubmit, onClose, loading, error }) {
  const [pin, setPin] = useState("");
  const demoPin = DEMO_PINS[role];

  useEffect(() => {
    setPin("");
  }, [role]);

  const submit = (event) => {
    event.preventDefault();
    if (pin.trim()) onSubmit(pin.trim());
  };

  return (
    <div className="role-pin-overlay" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="role-pin-modal" role="dialog" aria-modal="true" aria-labelledby="role-pin-title">
        <button className="role-pin-modal__close" type="button" onClick={onClose} aria-label="Close PIN dialog" title="Close">
          <IconX size={18} />
        </button>
        <span className="eyebrow">SECURE ROLE SWITCH</span>
        <h2 id="role-pin-title">Unlock {roleLabel}</h2>
        <p className="role-pin-modal__copy">Enter the workspace PIN to continue in this role.</p>

        <form onSubmit={submit} className="role-pin-form">
          <label className="field-label" htmlFor="workspace-role-pin">Workspace PIN</label>
          <input
            id="workspace-role-pin"
            className="text-input role-pin-modal__input"
            type="password"
            inputMode="numeric"
            autoComplete="off"
            autoFocus
            value={pin}
            onChange={(event) => setPin(event.target.value)}
            placeholder="Enter PIN"
          />
          <div className="role-pin-modal__hint">
            <IconCheckCircle size={15} />
            <span>Demo PIN: <b>{demoPin}</b></span>
          </div>

          {error && (
            <div className="login-error" role="alert">
              <IconAlertTriangle size={16} />
              <span>{error}</span>
            </div>
          )}

          <div className="role-pin-modal__actions">
            <button className="btn btn--ghost" type="button" onClick={onClose}>Cancel</button>
            <button className="btn btn--primary" type="submit" disabled={loading || !pin.trim()}>
              {loading ? "Verifying..." : "Unlock workspace"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}