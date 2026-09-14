const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("electronAPI", {
  safeStorage: {
    set: (key, value) => ipcRenderer.invoke("safeStorage:set", key, value),
    get: (key) => ipcRenderer.invoke("safeStorage:get", key),
    remove: (key) => ipcRenderer.invoke("safeStorage:remove", key),
  },
});
