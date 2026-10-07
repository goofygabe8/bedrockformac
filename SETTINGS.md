# Launcher settings

Open **Minecraft Bedrock → Settings…**. Changes apply at the next game start, so you can save them while playing. The launcher backs up changed Minecraft options locally before applying them.

## Recommended starting point

**Balanced** uses High Resolution / Retina, Metal 3, Fancy graphics, 4× anti-aliasing, a 16-chunk classic render distance, vertical sync, and a 120 FPS cap. Performance uses a lower resolution and draw distance with a 60 FPS cap. Quality uses Vibrant Visuals and a longer draw distance. Actual frame rates depend on your Mac, the world, and resource packs.

These presets change graphics controls only. **Restore Defaults** selects the recommended value for every setting. Click **Save Settings** to keep a preset or restored defaults. Updating the launcher keeps existing Minecraft preferences.

## Metal 3 and Metal 4

The original Mac showed blue, translucent server UI with MSAA on the D3DMetal 4.0b2 Metal 4 backend. The user confirmed that Metal 3 with 4× MSAA corrects it. The exact runtime defect is not established, and performance differences have not been measured. Metal 3 remains the compatibility default; Metal 4 is experimental and can reproduce that issue.

MetalFX frame interpolation is a separate integration, and is [available with both Metal 3 and Metal 4](https://developer.apple.com/metal/Metal-Feature-Set-Tables.pdf). This launcher does not implement frame generation.

## Display

| Setting | Recommended | What it does |
| --- | --- | --- |
| High Resolution / Retina | On | Use the full pixel resolution of Retina displays. Sharper text and edges; more GPU work. Applies after restarting Minecraft. |
| Fullscreen | Off | Start Minecraft in fullscreen instead of a window. |
| Vertical sync | On | Keep frames in step with your display to reduce tearing. Can add some input delay. |
| Frame rate limit | 120 FPS | A lower cap reduces heat and battery use. Vertical sync may cap the rate further. |
| Field of view | 70° | Show more of the world at higher values, with stronger perspective distortion. |
| Interface scale | Automatic | Change the size of inventory and menu elements. Available sizes depend on the game window. |
| HUD opacity | 100% | Make the hotbar and HUD more opaque. 100% is recommended for clear menus. |

## Graphics

| Setting | Recommended | What it does |
| --- | --- | --- |
| Graphics renderer | Metal 3 (Recommended) | Metal 3 fixes the server UI tint with anti-aliasing. Experimental Metal 4 reproduced that bug on the original Mac. |
| Graphics mode | Fancy | Fancy is the balanced default. Vibrant Visuals adds lighting effects and costs more GPU time; some server packs disable it. |
| Anti-aliasing | 4× (Recommended) | Smooth jagged edges in Simple or Fancy graphics. Higher values cost more GPU time. The slider can be hidden in Vibrant Visuals. |
| Classic render distance | 16 chunks | How far the game draws in Simple or Fancy mode. Larger distances use more CPU, GPU, and memory. |
| Vibrant render distance | 16 chunks | Draw distance used by Vibrant Visuals. Keep this lower than the classic distance for smoother play. |
| Display brightness | 50% | Adjust Minecraft display brightness. This does not change the Mac display brightness. |
| Texture streaming | On | Allow textures to load as needed instead of keeping everything resident. Recommended on Macs with limited memory. |
| Multi-threaded renderer | On | Let Minecraft use multiple CPU threads for rendering work. Leave enabled unless diagnosing a game-specific problem. |
| Performance overlay | Off | Show Apple’s Metal performance overlay, including frame rate and GPU timing. Useful when comparing settings. |

## Controls

| Setting | Recommended | What it does |
| --- | --- | --- |
| Mouse sensitivity | 50% | Camera movement speed for your mouse or trackpad. |
| Controller sensitivity | 50% | Camera movement speed for the controller’s right stick. |
| Invert mouse look | Off | Reverse vertical camera movement for mouse and trackpad input. |
| Invert controller look | Off | Reverse vertical camera movement for the controller’s right stick. |
| Auto-jump with keyboard | Off | Automatically jump over blocks while walking with keyboard controls. |
| Auto-jump with controller | Off | Automatically jump over blocks while walking with a controller. |
| Toggle crouch with keyboard | Off | Press crouch once to stay crouched; press again to stand. Otherwise hold the key. |
| Toggle crouch with controller | Off | Press crouch once to stay crouched; press again to stand. Otherwise hold the button. |
| Swap controller A / B | Off | Swap the game’s A and B actions for controllers with a different button layout. |
| Swap controller X / Y | Off | Swap the game’s X and Y actions for controllers with a different button layout. |
| Walking camera bob | On | Move the camera slightly as you walk. Disable for a steadier view. |
| Damage camera shake | On | Shake the camera when taking damage. Disable for a steadier view. |

## Sound

| Setting | Recommended | What it does |
| --- | --- | --- |
| Master volume | 70% | Volume for master volume. Audio output device is selected with Audio Output in the main launcher. |
| Music | 30% | Volume for music. Audio output device is selected with Audio Output in the main launcher. |
| Sound effects | 100% | Volume for sound effects. Audio output device is selected with Audio Output in the main launcher. |
| Ambient sounds | 100% | Volume for ambient sounds. Audio output device is selected with Audio Output in the main launcher. |
| Blocks | 100% | Volume for blocks. Audio output device is selected with Audio Output in the main launcher. |
| Hostile creatures | 100% | Volume for hostile creatures. Audio output device is selected with Audio Output in the main launcher. |
| Friendly creatures | 100% | Volume for friendly creatures. Audio output device is selected with Audio Output in the main launcher. |
| Player sounds | 100% | Volume for player sounds. Audio output device is selected with Audio Output in the main launcher. |
| Weather | 100% | Volume for weather. Audio output device is selected with Audio Output in the main launcher. |
| Jukebox and note blocks | 100% | Volume for jukebox and note blocks. Audio output device is selected with Audio Output in the main launcher. |

## Audio output and game controls

**Audio Output…** opens the runtime’s Audio tab for selecting an output device. Device changes apply after restarting Minecraft. Volume controls are in the Sound tab.

**Close Game** sends a normal close request. Finish any save or confirmation shown by Minecraft. **Show Game** activates its window. **Open Game Logs** opens the local diagnostics folder; review logs before sharing them.
