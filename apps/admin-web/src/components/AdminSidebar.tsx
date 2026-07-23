export function AdminSidebar() {
  return (
    <aside className="w-64 bg-gray-900 text-white h-screen p-4">
      <div className="mb-8">
        <h1 className="text-xl font-bold">iBreeze Admin</h1>
        <p className="text-sm text-gray-400">Management Console</p>
      </div>
      <nav>
        <ul className="space-y-2">
          <li><a href="/dashboard" className="block p-2 rounded hover:bg-gray-800">Dashboard</a></li>
          <li><a href="/users" className="block p-2 rounded hover:bg-gray-800">Users</a></li>
          <li><a href="/skills" className="block p-2 rounded hover:bg-gray-800">Skills</a></li>
          <li><a href="/catalog" className="block p-2 rounded hover:bg-gray-800">Catalog</a></li>
          <li><a href="/audit" className="block p-2 rounded hover:bg-gray-800">Audit Logs</a></li>
          <li><a href="/settings" className="block p-2 rounded hover:bg-gray-800">Settings</a></li>
        </ul>
      </nav>
    </aside>
  );
}
