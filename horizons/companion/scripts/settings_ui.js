import {world, system, ItemStack, CommandPermissionLevel} from "@minecraft/server";
import {ActionFormData, ModalFormData, FormCancelationReason} from "@minecraft/server-ui";

export const BOOK = "bhl:settings_book";
const PROPERTY = "bhl:client_settings";
const DEFAULTS = Object.freeze({enabled: true, distance: 512, near: 256, quads: 768, approximate: false, skirts: true});
const openForms = new Set();
let hooks;

export function validateSettings(value) {
  if (!value || ["enabled", "approximate", "skirts"].some(key => typeof value[key] !== "boolean") ||
      !Number.isInteger(value.distance) || value.distance < 128 || value.distance > 1024 ||
      !Number.isInteger(value.near) || value.near < 16 || value.near >= value.distance ||
      !Number.isInteger(value.quads) || value.quads < 128 || value.quads > 2048) throw new Error("Invalid Horizons settings.");
  return Object.fromEntries(Object.keys(DEFAULTS).map(key => [key, value[key]]));
}
export function savedSettings(player) {
  try {
    const text = player.getDynamicProperty(PROPERTY);
    if (typeof text === "string" && text.length <= 1024) return validateSettings(JSON.parse(text));
  } catch (_) {}
  return {...DEFAULTS};
}
export function hasSavedSettings(player) { return typeof player.getDynamicProperty(PROPERTY) === "string"; }
export function storeSettings(player, value, notify = true) {
  const settings = validateSettings(value);
  player.setDynamicProperty(PROPERTY, JSON.stringify(settings));
  const sent = hooks.sendSettings(player, settings);
  if (notify) hooks.notice(player, sent ? "Settings saved and sent to your client." :
    "Settings saved. The native client is not connected: load your installed client mod, then use .horizons realm on. The book cannot supply the renderer.");
  return settings;
}
export function giveBook(player) {
  const inventory = player.getComponent("minecraft:inventory")?.container;
  if (!inventory) throw new Error("Your inventory is unavailable.");
  for (let slot = 0; slot < inventory.size; slot++) {
    if (inventory.getItem(slot)?.typeId === BOOK) { hooks.notice(player, "Your settings book is already in your inventory. Hold it and use it."); return; }
  }
  if (inventory.emptySlotsCount === 0) throw new Error("Make one empty inventory slot for the settings book.");
  const book = new ItemStack(BOOK, 1);
  book.setLore(["Use to open Horizons settings", "Or type /bhl:menu", "Free replacement: /bhl:book"]);
  if (inventory.addItem(book)) throw new Error("Could not add the settings book. Make an empty slot and retry.");
  hooks.notice(player, "Settings book added. Hold it and use it. You can also craft one from one paper.");
}
async function display(form, player) {
  for (let attempt = 0; attempt < 5; attempt++) {
    if (!player.isValid) return undefined;
    const response = await form.show(player);
    if (response.cancelationReason !== FormCancelationReason.UserBusy) return response;
    await system.waitTicks(10);
  }
  hooks.notice(player, "Close chat or other menus, then use the book again.");
  return undefined;
}
async function clientSettings(player) {
  const s = savedSettings(player);
  const form = new ModalFormData().title("Horizons • Your Settings")
    .toggle("Draw distant terrain", {defaultValue: s.enabled, tooltip: "Stops or resumes distant geometry. A working native renderer is required."})
    .slider("Maximum distance (blocks)", 128, 1024, {defaultValue: s.distance, valueStep: 16, tooltip: "Larger distances request more tiles and use more CPU/GPU. Start at 512."})
    .slider("Near cutoff (blocks)", 16, 1008, {defaultValue: s.near, valueStep: 16, tooltip: "Match Minecraft's normal render distance: chunks × 16. This is clamped below the maximum distance."})
    .slider("Geometry budget", 128, 2048, {defaultValue: s.quads, valueStep: 128, tooltip: "Maximum distant quads per frame. 768 is balanced; lower values reduce rendering cost."})
    .toggle("Approximate visited terrain", {defaultValue: s.approximate, tooltip: "Client-only observations can include partially loaded chunks. Off uses verified companion data."})
    .toggle("Hide tile edge seams", {defaultValue: s.skirts, tooltip: "Adds small terrain skirts at tile edges. Uses some of the geometry budget."})
    .submitButton("Save Settings");
  const result = await display(form, player);
  if (!result || result.canceled) return;
  const [enabled, distance, near, quads, approximate, skirts] = result.formValues;
  storeSettings(player, {enabled, distance, near: Math.min(near, distance - 16), quads, approximate, skirts});
}
async function presets(player) {
  const result = await display(new ActionFormData().title("Horizons • Presets")
    .body("These change your distant terrain settings. Near cutoff assumes Minecraft renders 16 chunks; adjust it if needed.")
    .button("Balanced • 512 blocks / 768 quads")
    .button("Performance • 384 blocks / 384 quads")
    .button("Quality • 768 blocks / 1536 quads"), player);
  if (!result || result.canceled) return;
  const preset = [[512, 768], [384, 384], [768, 1536]][result.selection];
  if (preset) storeSettings(player, {...DEFAULTS, distance: preset[0], quads: preset[1]});
}
function operator(player) { return player.commandPermissionLevel >= CommandPermissionLevel.Admin; }
async function generationSettings(player) {
  if (!operator(player)) { hooks.notice(player, "Only the world operator can change ahead-of-visit generation."); return; }
  const result = await display(new ModalFormData().title("Horizons • World Settings")
    .toggle("Allow ahead-of-visit sampling", {defaultValue: hooks.state(player).generation,
      tooltip: "Loads and generates real chunks when connected native clients request them. Uses server time and world storage. Applies to everyone."})
    .submitButton("Save World Setting"), player);
  if (!result || result.canceled) return;
  if (!operator(player)) throw new Error("Operator permission is required.");
  hooks.setGeneration(player, result.formValues[0]);
}
const HELP = ".horizons status\n.horizons on / off\n.horizons distance 512\n.horizons near 256\n.horizons quads 768\n.horizons approximate on / off\n.horizons skirts on / off\n.horizons realm on / off\n.horizons generation on / off (operator)\n.horizons menu / book\n\nWithout a native client: /bhl:menu and /bhl:book still work. The book cannot install or replace the native renderer.";
export async function openMenu(player) {
  if (!hooks || !player.isValid || openForms.has(player.id)) return;
  const id = player.id; openForms.add(id);
  try {
    const state = hooks.state(player);
    const choices = ["Distant Renderer Settings", "Renderer Presets", "Device Support & Connection", "Chat Commands", "Get Settings Book"];
    if (operator(player)) choices.push("World Generation • Operator");
    const menu = new ActionFormData().title("Horizons Settings Book")
      .body(`Client handshake: ${state.connected ? "connected (rendering still needs confirmation)" : "not connected"}\nWorld generation: ${state.generation ? "allowed" : "off"}\n\nBook menus work on consoles, phones and computers. Extra distant terrain requires the native computer client; Realm packs cannot install it on consoles. Settings are saved for you in this world.`);
    choices.forEach(choice => menu.button(choice));
    const result = await display(menu, player);
    if (!result || result.canceled) return;
    if (result.selection === 0) await clientSettings(player);
    else if (result.selection === 1) await presets(player);
    else if (result.selection === 2) await display(new ActionFormData().title("Horizons • Connection")
      .body("Xbox, PlayStation, Switch and mobile: the Realm supplies this book and its menus. Extra distant rendering is unavailable on these standard clients.\n\nSupported computer client: install the matching native mod. On Bedrock for Mac, installed client mods load with Minecraft. Then join this world and type .horizons realm on.\n\n/bhl:config true only permits sampling. It does not load the client or draw terrain. A Realm owner must install this companion on the Realm. Library loading, a handshake, and visible terrain are separate checks.").button("OK"), player);
    else if (result.selection === 3) await display(new ActionFormData().title("Horizons • Commands").body(HELP).button("OK"), player);
    else if (result.selection === 4) giveBook(player);
    else if (result.selection === 5 && choices.length > 5) await generationSettings(player);
  } catch (error) { hooks.notice(player, String(error?.message ?? "Settings menu unavailable.").slice(0, 160)); }
  finally { openForms.delete(id); }
}
export function initializeSettingsUI(callbacks) {
  hooks = callbacks;
  world.beforeEvents.itemUse.subscribe(event => {
    if (event.itemStack.typeId !== BOOK) return;
    event.cancel = true; const player = event.source;
    system.run(() => { void openMenu(player); });
  });
  world.afterEvents.playerLeave.subscribe(event => openForms.delete(event.playerId));
  world.afterEvents.playerSpawn.subscribe(event => {
    if (!event.initialSpawn) return;
    const player = event.player;
    system.runTimeout(() => {
      if (!player.isValid || player.getDynamicProperty("bhl:book_received") === true) return;
      try {
        giveBook(player);
        player.setDynamicProperty("bhl:book_received", true);
      } catch (_) { hooks.notice(player, "Use /bhl:book when you have an empty inventory slot, or craft the settings book from one paper."); }
    }, 40);
  });
}
