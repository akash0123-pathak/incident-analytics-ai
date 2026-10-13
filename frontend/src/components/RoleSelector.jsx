export default function RoleSelector({ roles, selectedRole, onChange }) {
  return (
    <div className="panel-block">
      <div className="panel-block__label">Viewing as</div>
      <select className="role-select" value={selectedRole} onChange={(event) => onChange(event.target.value)} aria-label="Switch workspace role">
        {roles.map((role) => <option key={role.id} value={role.id}>{role.label}</option>)}
      </select>
      <small className="role-select__hint">Manager and Executive require their PIN.</small>
    </div>
  );
}
