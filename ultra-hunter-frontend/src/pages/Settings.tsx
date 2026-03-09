import { useEffect, useState } from "react";
import { Save, Eye, EyeOff, TestTube, RefreshCw, Shield } from "lucide-react";
import { settingsApi, actionsApi, schedulerApi } from "../lib/api";

interface SettingsState {
  firecrawl_api_key_1: string;
  firecrawl_api_key_2: string;
  gemini_api_key: string;
  telegram_bot_token: string;
  telegram_chat_id: string;
  monitoring_enabled: string;
}

const defaultSettings: SettingsState = {
  firecrawl_api_key_1: "",
  firecrawl_api_key_2: "",
  gemini_api_key: "",
  telegram_bot_token: "",
  telegram_chat_id: "",
  monitoring_enabled: "true",
};

export default function Settings() {
  const [settings, setSettings] = useState<SettingsState>(defaultSettings);
  const [showKeys, setShowKeys] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      const { settings: raw } = await settingsApi.getSettingsRaw();
      setSettings({ ...defaultSettings, ...raw });
    } catch (err) {
      console.error("Failed to load settings:", err);
      showMessage("error", "Failed to load settings");
    } finally {
      setLoading(false);
    }
  };

  const showMessage = (type: "success" | "error", text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 4000);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await settingsApi.updateBatch(settings as unknown as Record<string, string>);
      showMessage("success", "Settings saved successfully!");
    } catch (err) {
      console.error("Failed to save:", err);
      showMessage("error", "Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

  const handleTestTelegram = async () => {
    setTesting(true);
    try {
      await actionsApi.testTelegram();
      showMessage("success", "Test notification sent! Check your Telegram.");
    } catch (err) {
      console.error("Telegram test failed:", err);
      showMessage("error", "Failed to send test notification. Check your bot token and chat ID.");
    } finally {
      setTesting(false);
    }
  };

  const handleToggleMonitoring = async () => {
    try {
      const newState = settings.monitoring_enabled === "true" ? "false" : "true";
      if (newState === "true") {
        await schedulerApi.start();
      } else {
        await schedulerApi.stop();
      }
      setSettings((prev) => ({ ...prev, monitoring_enabled: newState }));
      showMessage("success", `Monitoring ${newState === "true" ? "started" : "stopped"}`);
    } catch (err) {
      console.error("Toggle monitoring failed:", err);
      showMessage("error", "Failed to toggle monitoring");
    }
  };

  const toggleShowKey = (key: string) => {
    setShowKeys((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const updateField = (key: keyof SettingsState, value: string) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 animate-spin text-cyan-400" />
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-3xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Settings</h1>
          <p className="text-sm text-gray-400">
            Configure API keys, Telegram, and monitoring preferences
          </p>
        </div>
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 px-4 py-2 bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white rounded-lg transition-colors"
        >
          <Save className="w-4 h-4" />
          {saving ? "Saving..." : "Save All"}
        </button>
      </div>

      {message && (
        <div className={`p-3 rounded-lg text-sm ${
          message.type === "success"
            ? "bg-green-500/20 text-green-400 border border-green-500/30"
            : "bg-red-500/20 text-red-400 border border-red-500/30"
        }`}>
          {message.text}
        </div>
      )}

      {/* Monitoring Control */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-5">
        <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <Shield className="w-5 h-5 text-cyan-400" />
          Monitoring Control
        </h2>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-white font-medium">Auto-Monitoring</p>
            <p className="text-sm text-gray-400">Enable/disable the monitoring scheduler</p>
          </div>
          <button
            onClick={handleToggleMonitoring}
            className={`relative w-14 h-7 rounded-full transition-colors ${
              settings.monitoring_enabled === "true" ? "bg-cyan-600" : "bg-gray-700"
            }`}
          >
            <span className={`absolute top-0.5 left-0.5 w-6 h-6 rounded-full bg-white transition-transform ${
              settings.monitoring_enabled === "true" ? "translate-x-7" : ""
            }`} />
          </button>
        </div>
      </div>

      {/* Firecrawl API Keys */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-5">
        <h2 className="text-lg font-semibold text-white mb-1">Firecrawl API Keys</h2>
        <p className="text-sm text-gray-400 mb-4">Used for web scraping. Keys rotate automatically.</p>
        <div className="space-y-3">
          <SecretField
            label="API Key 1"
            value={settings.firecrawl_api_key_1}
            show={showKeys.firecrawl_api_key_1}
            onToggle={() => toggleShowKey("firecrawl_api_key_1")}
            onChange={(v) => updateField("firecrawl_api_key_1", v)}
            placeholder="fc-..."
          />
          <SecretField
            label="API Key 2"
            value={settings.firecrawl_api_key_2}
            show={showKeys.firecrawl_api_key_2}
            onToggle={() => toggleShowKey("firecrawl_api_key_2")}
            onChange={(v) => updateField("firecrawl_api_key_2", v)}
            placeholder="fc-..."
          />
        </div>
      </div>

      {/* Gemini API Key */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-5">
        <h2 className="text-lg font-semibold text-white mb-1">Google Gemini API Key</h2>
        <p className="text-sm text-gray-400 mb-4">Used for AI classification of updates.</p>
        <SecretField
          label="Gemini API Key"
          value={settings.gemini_api_key}
          show={showKeys.gemini_api_key}
          onToggle={() => toggleShowKey("gemini_api_key")}
          onChange={(v) => updateField("gemini_api_key", v)}
          placeholder="AIza..."
        />
      </div>

      {/* Telegram Configuration */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-5">
        <h2 className="text-lg font-semibold text-white mb-1">Telegram Notifications</h2>
        <p className="text-sm text-gray-400 mb-4">Configure your Telegram bot for instant alerts.</p>
        <div className="space-y-3">
          <SecretField
            label="Bot Token"
            value={settings.telegram_bot_token}
            show={showKeys.telegram_bot_token}
            onToggle={() => toggleShowKey("telegram_bot_token")}
            onChange={(v) => updateField("telegram_bot_token", v)}
            placeholder="123456789:AAH..."
          />
          <div>
            <label className="block text-sm text-gray-400 mb-1">Chat ID</label>
            <input
              type="text"
              value={settings.telegram_chat_id}
              onChange={(e) => updateField("telegram_chat_id", e.target.value)}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm focus:border-cyan-500 focus:outline-none"
              placeholder="7779346815"
            />
          </div>
          <button
            onClick={handleTestTelegram}
            disabled={testing}
            className="flex items-center gap-2 px-3 py-2 text-sm bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white rounded-lg transition-colors"
          >
            <TestTube className="w-4 h-4" />
            {testing ? "Sending..." : "Send Test Notification"}
          </button>
        </div>
      </div>

      {/* Baby Steps Instructions */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-5">
        <h2 className="text-lg font-semibold text-white mb-3">Setup Instructions</h2>
        <div className="space-y-4 text-sm">
          <div>
            <h3 className="text-cyan-400 font-medium mb-1">Telegram Bot Setup</h3>
            <ol className="list-decimal list-inside text-gray-400 space-y-1">
              <li>Open Telegram, search for <span className="text-white">@BotFather</span></li>
              <li>Send <span className="text-white font-mono">/newbot</span></li>
              <li>Choose a name (e.g., Manus Ultra Hunter)</li>
              <li>Choose a username ending in <span className="text-white font-mono">bot</span></li>
              <li>Copy the <span className="text-white">Bot Token</span> and paste above</li>
              <li>Message your bot, then visit: <span className="text-cyan-400 break-all">api.telegram.org/bot&lt;TOKEN&gt;/getUpdates</span></li>
              <li>Find your <span className="text-white">Chat ID</span> in the response</li>
            </ol>
          </div>
          <div>
            <h3 className="text-cyan-400 font-medium mb-1">Firecrawl API</h3>
            <ol className="list-decimal list-inside text-gray-400 space-y-1">
              <li>Go to <span className="text-cyan-400">firecrawl.dev</span> and sign up</li>
              <li>Get your API key from the dashboard</li>
              <li>Paste it above (you can add 2 keys for rotation)</li>
            </ol>
          </div>
          <div>
            <h3 className="text-cyan-400 font-medium mb-1">Google Gemini</h3>
            <ol className="list-decimal list-inside text-gray-400 space-y-1">
              <li>Go to <span className="text-cyan-400">aistudio.google.com</span></li>
              <li>Click "Get API Key" and create one</li>
              <li>Paste the key above</li>
            </ol>
          </div>
        </div>
      </div>
    </div>
  );
}

function SecretField({
  label, value, show, onToggle, onChange, placeholder,
}: {
  label: string; value: string; show: boolean;
  onToggle: () => void; onChange: (v: string) => void; placeholder: string;
}) {
  return (
    <div>
      <label className="block text-sm text-gray-400 mb-1">{label}</label>
      <div className="flex gap-2">
        <input
          type={show ? "text" : "password"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="flex-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm focus:border-cyan-500 focus:outline-none font-mono"
          placeholder={placeholder}
        />
        <button
          onClick={onToggle}
          className="px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-gray-400 hover:text-white transition-colors"
        >
          {show ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
        </button>
      </div>
    </div>
  );
}
