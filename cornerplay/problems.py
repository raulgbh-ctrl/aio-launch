"""Why did that game close straight away? Read its log and say it in plain words.

explain(log_text) -> {"cause": str, "fix": "repair" | "vcrun" | "dotnet" | "proton" | "vulkan" | "", "detail": str}
or {} when nothing recognisable is in the log.
"""
import re

# (pattern, cause, fix, detail) — first match wins, most specific first.
RULES = [
    (r"No space left on device", "The drive is full", "storage",
     "The game could not write its files. Free some space and try again."),
    (r"VK_ERROR_INITIALIZATION_FAILED|vkEnumeratePhysicalDevices|No Vulkan|DXVK: No adapters|"
     r"Failed to create Vulkan instance|vulkan.*not supported", "No working Vulkan graphics", "vulkan",
     "Proton draws Windows games with Vulkan, and it found no GPU to use."),
    (r"(?i)easyanticheat|EasyAntiCheat_EOS|battleye|BEService", "Anti-cheat blocked it", "",
     "This game's anti-cheat does not allow Linux (the publisher has to turn that on). "
     "Single-player modes sometimes still work; check its ProtonDB page."),
    (r"(?i)(MSVCP1\d0|VCRUNTIME1\d0|vcruntime140_1|msvcr1\d0)\.dll", "Missing Visual C++ runtime", "vcrun",
     "The game needs Microsoft's Visual C++ runtime in its Proton prefix."),
    (r"(?i)mscoree\.dll|\.NET Framework|clr\.dll|mono.*not (found|installed)", "Missing .NET Framework", "dotnet",
     "The game (or its launcher) needs .NET in its Proton prefix."),
    (r"(?i)d3dcompiler_4[37]\.dll.*not found|Library d3dcompiler", "Missing DirectX shader compiler", "vcrun",
     "The game needs d3dcompiler from DirectX in its prefix."),
    (r"(?i)could not find .*\.exe|no such file or directory.*\.exe|File not found|Executable not found",
     "The game's files are missing or broken", "repair", "Checking and repairing the files usually fixes it."),
    (r"(?i)wine: Unhandled page fault|Unhandled exception: page fault|wine: Unhandled (illegal|privileged)",
     "The game crashed inside Proton", "proton",
     "Another Proton version often helps (a game's Options > Proton version); ProtonDB lists what works."),
    (r"(?i)err:module:import_dll Library (\S+\.dll)", "A Windows library is missing", "proton",
     "The log names a .dll the game needs; another Proton version, or ProtonDB's tips, usually help."),
]


def explain(text):
    if not text:
        return {}
    for pattern, cause, fix, detail in RULES:
        m = re.search(pattern, text)
        if m:
            if fix == "proton" and m.groups() and m.group(1):
                detail = f"It needs {m.group(1)}. " + detail
            return {"cause": cause, "fix": fix, "detail": detail}
    return {}
