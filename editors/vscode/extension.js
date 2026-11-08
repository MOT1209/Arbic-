// Starts `arabic debug --stdio` and lets VS Code speak DAP to it.
const vscode = require("vscode");

function activate(context) {
  context.subscriptions.push(
    vscode.debug.registerDebugAdapterDescriptorFactory("arabic", {
      createDebugAdapterDescriptor() {
        return new vscode.DebugAdapterExecutable("arabic", ["debug", "--stdio"]);
      },
    })
  );
}

module.exports = { activate };
