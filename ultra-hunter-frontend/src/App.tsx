import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import {
  LayoutDashboard, Radio, Bell, Settings as SettingsIcon,
  Zap, Shield
} from "lucide-react";
import Dashboard from "./pages/Dashboard";
import Sources from "./pages/Sources";
import Alerts from "./pages/Alerts";
import Settings from "./pages/Settings";

const navItems = [
  { path: "/", label: "Dashboard", icon: LayoutDashboard },
  { path: "/sources", label: "Sources", icon: Radio },
  { path: "/alerts", label: "Alerts", icon: Bell },
  { path: "/settings", label: "Settings", icon: SettingsIcon },
];

function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-950 text-white flex">
        {/* Sidebar */}
        <aside className="w-64 bg-gray-900 border-r border-gray-800 flex flex-col fixed h-full z-10">
          {/* Logo */}
          <div className="p-5 border-b border-gray-800">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-gradient-to-br from-cyan-500 to-blue-600 rounded-xl flex items-center justify-center">
                <Zap className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className="text-lg font-bold bg-gradient-to-r from-cyan-400 to-blue-400 bg-clip-text text-transparent">
                  Ultra Hunter
                </h1>
                <p className="text-xs text-gray-500">v3.5 + v4</p>
              </div>
            </div>
          </div>

          {/* Navigation */}
          <nav className="flex-1 p-3 space-y-1">
            {navItems.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                end={item.path === "/"}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-medium transition-all ${
                    isActive
                      ? "bg-cyan-600/20 text-cyan-400 border border-cyan-500/30"
                      : "text-gray-400 hover:text-white hover:bg-gray-800"
                  }`
                }
              >
                <item.icon className="w-5 h-5" />
                {item.label}
              </NavLink>
            ))}
          </nav>

          {/* Footer */}
          <div className="p-4 border-t border-gray-800">
            <div className="flex items-center gap-2 text-xs text-gray-500">
              <Shield className="w-4 h-4" />
              <span>Ethical Edition</span>
            </div>
            <p className="text-xs text-gray-600 mt-1">
              360° AI Event Intelligence
            </p>
          </div>
        </aside>

        {/* Main Content */}
        <main className="flex-1 ml-64 p-6 overflow-auto">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/sources" element={<Sources />} />
            <Route path="/alerts" element={<Alerts />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;
