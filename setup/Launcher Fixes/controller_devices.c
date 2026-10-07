/* Enumerate only gamepad VID/PIDs using the launcher's SDL2 runtime. */
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <unistd.h>
int main(int argc, char **argv) {
    if (argc != 2) return 2;
    void *lib = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
    if (!lib) return 3;
    int (*init)(unsigned) = dlsym(lib, "SDL_Init");
    int (*count)(void) = dlsym(lib, "SDL_NumJoysticks");
    int (*mapped)(int) = dlsym(lib, "SDL_IsGameController");
    void *(*open)(int) = dlsym(lib, "SDL_JoystickOpen");
    uint16_t (*vendor)(void *) = dlsym(lib, "SDL_JoystickGetVendor");
    uint16_t (*product)(void *) = dlsym(lib, "SDL_JoystickGetProduct");
    void (*close)(void *) = dlsym(lib, "SDL_JoystickClose");
    void (*pump)(void) = dlsym(lib, "SDL_PumpEvents");
    void (*quit)(void) = dlsym(lib, "SDL_Quit");
    if (!init || !count || !mapped || !open || !vendor || !product || !close || !pump || !quit) return 4;
    if (init(0x2000)) return 5;
    for (int k = 0; k < 3; k++) { pump(); usleep(100000); }
    for (int i = 0; i < count(); i++) {
        if (!mapped(i)) continue;
        void *joy = open(i);
        if (!joy) continue;
        uint16_t vid = vendor(joy), pid = product(joy);
        if (vid && pid) printf("%04x/%04x\n", vid, pid);
        close(joy);
    }
    quit();
    dlclose(lib);
    return 0;
}
