#Requires AutoHotkey v2.0
#SingleInstance Force
Persistent

; Opens the 문장 읽기 app, hides the mouse after it is still for IDLE_MS over an
; app window (focused or not), and quits once every app window has closed.
; Windows draws the blank cursor itself, so Chrome need not repaint.
IDLE_MS := 3000
GONE_MS := 3000
START_WAIT_MS := 30000
TITLE_PART := "문장 읽기"
BROWSERS := ["chrome.exe", "msedge.exe"]
APP_EXE := "C:\Program Files\Google\Chrome\Application\chrome_proxy.exe"
APP_ARGS := '--profile-directory="Profile 1" --app-id=gmcbhkpkpmofemkjpnnfknmkeojidgcp'
; design/451: the USB sync helper runs while the app is open.
BRIDGE := A_ScriptDir "\usb_sync_bridge.py"
bridgePid := 0

hidden := false
lastX := -1
lastY := -1
stillSince := A_TickCount
startedAt := A_TickCount
appSeen := false
goneSince := 0

SetTitleMatchMode(2)
CoordMode("Mouse", "Screen")
OnExit(Quit)
A_IconTip := "문장 읽기: 마우스 숨기기"
StartBridge()
if !AppOpen()
    Run('"' APP_EXE '" ' APP_ARGS)
SetTimer(Check, 100)
SetTimer(WatchApp, 500)

Check() {
    global hidden, lastX, lastY, stillSince
    MouseGetPos(&x, &y, &win)
    if (x != lastX || y != lastY) {
        lastX := x
        lastY := y
        stillSince := A_TickCount
        if hidden
            ShowCursor()
        return
    }
    if (hidden || A_TickCount - stillSince < IDLE_MS)
        return
    if OverApp(win)
        HideCursor()
}

WatchApp() {
    global appSeen, goneSince
    if AppOpen() {
        appSeen := true
        goneSince := 0
        return
    }
    if !appSeen {
        if (A_TickCount - startedAt > START_WAIT_MS)
            ExitApp()
        return
    }
    if !goneSince {
        goneSince := A_TickCount
        return
    }
    if (A_TickCount - goneSince >= GONE_MS)
        ExitApp()
}

AppOpen() {
    for name in BROWSERS {
        if WinExist(TITLE_PART " ahk_exe " name)
            return true
    }
    return false
}

OverApp(win) {
    try {
        title := WinGetTitle("ahk_id " win)
        exe := WinGetProcessName("ahk_id " win)
    } catch {
        return false
    }
    if !InStr(title, TITLE_PART)
        return false
    for name in BROWSERS {
        if (exe = name)
            return true
    }
    return false
}

Quit(*) {
    ShowCursor()
    StopBridge()
}

StartBridge() {
    global bridgePid
    if !FileExist(BRIDGE)
        return
    ; A second helper finds the ports taken and exits on its own.
    try Run('pythonw.exe "' BRIDGE '"', A_ScriptDir, "Hide", &bridgePid)
}

StopBridge() {
    global bridgePid
    if bridgePid
        try ProcessClose(bridgePid)
}

HideCursor() {
    global hidden
    ; 32x32 monochrome: AND all ones + XOR all zeros = see-through.
    andMask := Buffer(128, 0xFF)
    xorMask := Buffer(128, 0)
    for id in [32512, 32513, 32514, 32515, 32516, 32642, 32643, 32644, 32645, 32646, 32648, 32649, 32650, 32651] {
        h := DllCall("CreateCursor", "Ptr", 0, "Int", 0, "Int", 0, "Int", 32, "Int", 32
            , "Ptr", andMask, "Ptr", xorMask, "Ptr")
        DllCall("SetSystemCursor", "Ptr", h, "UInt", id)
    }
    hidden := true
}

ShowCursor() {
    global hidden
    ; SPI_SETCURSORS reloads the user's own cursor scheme.
    DllCall("SystemParametersInfo", "UInt", 0x57, "UInt", 0, "Ptr", 0, "UInt", 0)
    hidden := false
}
