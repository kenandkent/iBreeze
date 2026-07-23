export function Sidebar() {
  return (
    <aside className="w-64 bg-gray-900 text-white h-screen p-4">
      <div className="mb-8">
        <h1 className="text-xl font-bold">iBreeze</h1>
        <p className="text-sm text-gray-400">AI Company Desktop</p>
      </div>
      <nav>
        <ul className="space-y-2">
          <li><a href="/dashboard" className="block p-2 rounded hover:bg-gray-800">Dashboard</a></li>
          <li><a href="/conversations" className="block p-2 rounded hover:bg-gray-800">Conversations</a></li>
          <li><a href="/tasks" className="block p-2 rounded hover:bg-gray-800">Tasks</a></li>
          <li><a href="/workspace" className="block p-2 rounded hover:bg-gray-800">Workspace</a></li>
          <li><a href="/settings" className="block p-2 rounded hover:bg-gray-800">Settings</a></li>
        </ul>
      </nav>
    </aside>
  );
}
