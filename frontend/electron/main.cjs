/**
 * CohortOS Desk — double-click. Bundled API preferred; stay-signed-in via refresh token.
 */
const { app, BrowserWindow, ipcMain, safeStorage } = require("electron");
const path = require("path");
const { spawn } = require("child_process");
const fs = require("fs");
const crypto = require("crypto");

let apiProc = null;
const USER_DATA = app.getPath("userData");
const SAFE_DIR = path.join(USER_DATA, "secure");
const DATA_DIR = path.join(USER_DATA, "data");

function ensureDirs() {
  for (const d of [SAFE_DIR, DATA_DIR]) {
    if (!fs.existsSync(d)) fs.mkdirSync(d, { recursive: true });
  }
}

function readOrCreateSecret(file, bytes = 32) {
  const p = path.join(SAFE_DIR, file);
  if (fs.existsSync(p)) return fs.readFileSync(p, "utf8").trim();
  const v = crypto.randomBytes(bytes).toString("hex");
  fs.writeFileSync(p, v, { mode: 0o600 });
  return v;
}

function findApiBinary() {
  const names = process.platform === "win32" ? ["cohortos-api.exe", "cohortos-api"] : ["cohortos-api"];
  const dirs = [
    process.resourcesPath ? path.join(process.resourcesPath, "bin") : null,
    process.resourcesPath || null,
    path.join(__dirname, "..", "bin"),
    path.join(__dirname, "..", "..", "dist"),
  ].filter(Boolean);
  for (const dir of dirs) {
    for (const n of names) {
      const p = path.join(dir, n);
      if (fs.existsSync(p)) return p;
    }
  }
  return null;
}

function startLocalApi() {
  ensureDirs();
  const secret = process.env.COHORTOS_JWT_SECRET || readOrCreateSecret("jwt_secret.txt");
  const founder = process.env.COHORTOS_FOUNDER_TOKEN || readOrCreateSecret("founder_token.txt");
  const authDb = process.env.COHORTOS_AUTH_DB || path.join(DATA_DIR, "auth.db");
  const cloudDb = process.env.COHORTOS_CLOUD_DB || path.join(DATA_DIR, "cloud.db");

  const env = {
    ...process.env,
    COHORTOS_JWT_SECRET: secret,
    COHORTOS_FOUNDER_TOKEN: founder,
    COHORTOS_AUTH_DB: authDb,
    COHORTOS_CLOUD_DB: cloudDb,
    // Pilot: show OTP in API responses until real SMS is connected
    COHORTOS_TEST_EXPOSE_OTP: process.env.COHORTOS_TEST_EXPOSE_OTP || "1",
    COHORTOS_CORS_ORIGINS:
      process.env.COHORTOS_CORS_ORIGINS ||
      "http://127.0.0.1:8741,http://localhost:8741,file://",
  };

  const bin = findApiBinary();
  if (bin) {
    console.log("[CohortOS] bundled API", bin);
    apiProc = spawn(bin, [], { env, stdio: "inherit" });
  } else {
    console.warn("[CohortOS] no bundled API binary; using python3");
    const py = process.env.COHORTOS_PYTHON || "python3";
    const backend =
      process.env.COHORTOS_BACKEND ||
      (process.resourcesPath ? path.join(process.resourcesPath, "backend") : path.join(__dirname, "..", ".."));
    apiProc = spawn(
      py,
      ["-c", "from api.main import create_api_app_or_raise; import uvicorn; uvicorn.run(create_api_app_or_raise(), host='127.0.0.1', port=8741, log_level='warning')"],
      { cwd: backend, env, stdio: "inherit" }
    );
  }
  apiProc.on("exit", (code) => console.log("[CohortOS] API exited", code));
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 840,
    title: "CohortOS",
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      preload: path.join(__dirname, "preload.cjs"),
    },
  });
  const prodIndex = path.join(__dirname, "..", "dist", "index.html");
  if (process.env.COHORTOS_DEV === "1") {
    win.loadURL(process.env.COHORTOS_DEV_URL || "http://127.0.0.1:5173");
  } else if (fs.existsSync(prodIndex)) {
    win.loadFile(prodIndex);
  } else {
    win.loadURL("http://127.0.0.1:8741/");
  }
}

ipcMain.handle("safeStorage:set", (_e, key, value) => {
  ensureDirs();
  if (safeStorage.isEncryptionAvailable()) {
    fs.writeFileSync(path.join(SAFE_DIR, key + ".bin"), safeStorage.encryptString(String(value)));
  } else {
    fs.writeFileSync(path.join(SAFE_DIR, key + ".txt"), String(value), "utf8");
  }
  return true;
});
ipcMain.handle("safeStorage:get", (_e, key) => {
  ensureDirs();
  const bin = path.join(SAFE_DIR, key + ".bin");
  const txt = path.join(SAFE_DIR, key + ".txt");
  if (fs.existsSync(bin) && safeStorage.isEncryptionAvailable()) {
    return safeStorage.decryptString(fs.readFileSync(bin));
  }
  if (fs.existsSync(txt)) return fs.readFileSync(txt, "utf8");
  return null;
});
ipcMain.handle("safeStorage:remove", (_e, key) => {
  ensureDirs();
  for (const ext of [".bin", ".txt"]) {
    const p = path.join(SAFE_DIR, key + ext);
    if (fs.existsSync(p)) fs.unlinkSync(p);
  }
  return true;
});
ipcMain.handle("cohortos:apiBase", () => "http://127.0.0.1:8741");

app.whenReady().then(() => {
  startLocalApi();
  setTimeout(createWindow, 1200);
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (apiProc) try { apiProc.kill(); } catch (_) {}
  if (process.platform !== "darwin") app.quit();
});
