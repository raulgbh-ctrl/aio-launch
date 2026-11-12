import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Effects
import QtQuick.Shapes
import QtQuick.Dialogs
import "protondb.js" as ProtonDB

ApplicationWindow {
    id: win
    width: 1320
    height: 840
    minimumWidth: 760
    minimumHeight: 480
    title: qsTr("Cornerplay")
    // With "Keep running in the tray" closing only hides the window; otherwise it quits (the
    // app no longer quits by itself when its last window closes: it may be sitting in the tray).
    onClosing: (close) => { if (app.keepInTray()) { close.accepted = false; win.hide() } else Qt.quit() }
    color: theme.background

    readonly property var theme: app.theme
    property bool tv: startTv
    property bool hiddenAtStart: startHidden  // started with the PC: in the tray until opened (tray.py)
    visibility: hiddenAtStart ? Window.Hidden : tv ? Window.FullScreen : Window.Windowed
    onTvChanged: { if (tv) tvUsed = true; else grid.forceActiveFocus() }
    property string selectedKey: ""
    property var selected: ({})

    // The theme with a game's own colour as its accent (see app.gameColour); unchanged for "".
    function tinted(accent) {
        if (!accent) return win.theme
        const c = Qt.darker(accent, 1.0)
        const lum = 0.299 * c.r + 0.587 * c.g + 0.114 * c.b
        return Object.assign({}, win.theme, { primary: accent, onPrimary: lum > 0.55 ? "#1b1b1f" : "#ffffff",
                                              primaryContainer: Qt.tint(win.theme.surfaceContainerHigh, Qt.alpha(accent, 0.3)) })
    }

    function select(key) {
        selectedKey = key
        selected = app.game(key)
        if (selected.key) detail.open()
    }
    // Play straight away when it is clear which copy to start; otherwise open the game's panel.
    function activate(key) {
        const target = app.launchTarget(key)
        if (target) { app.play(target); return }
        select(key)
        const g = app.game(key)
        if (g.copies.filter(c => c.installed).length > 1)
            toasts.append({ message: qsTr("Installed from several stores: pick the launcher to use") })
    }
    // Home sections: folded away or not, and their order (Settings keys home_collapsed / home_order).
    function homeFolded(id) { return (app.settingsMap.home_collapsed || []).indexOf(id) !== -1 }
    function toggleHome(id) {
        const now = (app.settingsMap.home_collapsed || []).slice()
        const i = now.indexOf(id)
        if (i === -1) now.push(id); else now.splice(i, 1)
        app.setSetting("home_collapsed", now)
    }
    function moveHome(id, step) {
        const order = (app.settingsMap.home_order || ["continue", "free"]).slice()
        const i = order.indexOf(id), j = i + step
        if (i < 0 || j < 0 || j >= order.length) return
        order[i] = order[j]; order[j] = id
        app.setSetting("home_order", order)
    }
    // The cover under the pointer: its colour tints the library; resting on it shows a preview.
    property bool showFilters: false
    property string hoverKey: ""
    property string hoverAccent: ""
    Connections { target: app; function onGameColourReady(key, colour) { if (key === win.hoverKey) win.hoverAccent = colour } }
    Timer {
        id: previewTimer
        interval: 700
        onTriggered: {
            const card = grid.itemAtIndex(grid.hoverIndex)
            if (!card || popupOpen || !win.cardsLive) return
            preview.g = app.game(win.hoverKey)
            const right = card.mapToItem(win.contentItem, card.width - 4, 18)
            const left = card.mapToItem(win.contentItem, 4, 18)
            preview.x = right.x + preview.width < win.width - 8 ? right.x : left.x - preview.width
            preview.y = Math.max(12, Math.min(right.y, win.height - preview.height - 12))  // always inside the window
            preview.visible = true
        }
    }
    function storeInfo(id) {
        const all = app.storesInfo
        for (let i = 0; i < all.length; i++) if (all[i].id === id) return all[i]
        return {}
    }

    onActiveChanged: if (active) app.windowActivated()

    Connections {
        target: app
        function onGameChanged(key) {
            if (win.selectedKey && (key === "" || key === win.selectedKey)) {
                const g = app.game(win.selectedKey)
                if (g.key) win.selected = g
                else detail.close()
            }
        }
        function onToast(message) { toasts.append({ message: message }) }
        function onLoginWeb(store, name, url) {
            if (store === "blizzard") {
                blizzardSync.active = true
                if (!blizzardLogin.item)
                    blizzardLogin.setSource("LoginWindow.qml", { keptProfile: blizzardSync.item.profile })
                blizzardLogin.item.begin(store, name, url)
                return
            }
            loginWindow.active = true
            loginWindow.item.begin(store, name, url)
        }
        function onBlizzardSync() {
            blizzardSync.active = true
            blizzardSync.item.start()
        }
        function onBlizzardForget() {
            blizzardSync.active = true
            app.blizzardClearCookies(blizzardSync.item.profile)
        }
        function onLoginReady(store, url, prompt) {
            login.store = store; login.url = url; login.prompt = prompt
            login.error = ""; login.busy = false
            code.text = ""
            login.open()
            app.openUrl(url)
        }
        function onLoginDone(store, ok, message) {
            if (store === "blizzard") { if (ok) toasts.append({ message: message }); return }
            login.busy = false
            if (ok) { login.close(); toasts.append({ message: message }) }
            else login.error = message
        }
    }

    Shortcut { sequence: "Ctrl+F"; onActivated: search.forceActiveFocus() }
    Shortcut { sequence: "Ctrl+R"; onActivated: app.refresh("", true) }
    Shortcut { sequence: "F5"; onActivated: app.refresh("", true) }
    Shortcut { sequence: "F11"; onActivated: win.tv = !win.tv }
    Shortcut { sequence: "F10"; enabled: !win.tv; onActivated: win.tv = true }  // the controller's Guide button
    Shortcut { sequence: "Ctrl+Q"; onActivated: Qt.quit() }

    // TV mode is built the first time it is opened (it costs ~45 ms at start otherwise), then kept.
    property bool tvUsed: startTv

    // The banner shows one of the last few games played, turning to the next every 9 s.
    property int heroAt: 0
    // The banner shows the last game you played (still: the others are in Continue playing below).
    readonly property int heroCount: Math.min(1, app.recentGames.length)
    readonly property var heroInfo: heroCount ? app.recentGames[heroAt % heroCount] : ({})
    property bool heroPaused: false
    Timer {
        interval: 9000
        repeat: true
        running: win.heroCount > 1 && !win.heroPaused && win.active && !win.tv && !win.popupOpen
        onTriggered: win.heroAt = (win.heroAt + 1) % win.heroCount
    }

    // Any pop-up open over the library? Cards and tiles then ignore the pointer, and keep
    // ignoring it for a moment after the pop-up closes (the click that closed it must not
    // land on the game underneath).
    readonly property bool popupOpen: detail.visible || gameOpts.visible || dlc.visible || accounts.visible
                                      || prefs.visible || viewer.visible || conflict.visible || login.visible
                                      || viewMenu.visible || gameMenu.visible
    property bool justClosed: false
    onPopupOpenChanged: {
        if (!popupOpen) { justClosed = true; closeGuard.restart() }
        else { trailerWait.stop(); trailerKey = ""; trailerUrl = "" }  // no trailer behind a pop-up
    }
    Timer { id: closeGuard; interval: 450; onTriggered: win.justClosed = false }
    readonly property bool cardsLive: !popupOpen && !justClosed
    Loader {
        id: tvLoader
        anchors.fill: parent
        z: 50
        active: win.tvUsed
        opacity: win.tv ? 1 : 0
        visible: opacity > 0
        Behavior on opacity { enabled: !app.light; NumberAnimation { duration: 280; easing.type: Easing.InOutQuad } }
        enabled: win.tv
        focus: win.tv
        sourceComponent: TvView {
            focus: true
            theme: win.theme
            shown: win.shown
            onExit: win.tv = false
        }
    }
    LaunchCard { theme: win.theme; blurSource: win.tv ? tvLoader.item : mainArea }  // the launch moment, over the library and TV mode alike

    // Follow wallpaper: the wallpaper itself, blurred and dimmed, behind the window, so Cornerplay
    // sits in the desktop like a pane of frosted glass. app.wallpaperPath is already a small,
    // blurred copy (made once, in the background), so this is a plain picture: no GPU effect.
    readonly property bool backdropOn: app.settingsMap.theme_mode === "ryoku" && app.settingsMap.wallpaper_backdrop !== false
                                       && app.wallpaperPath !== ""
    Item {
        id: backdrop
        anchors.fill: parent
        visible: win.backdropOn && !win.tv
        opacity: wallImage.status === Image.Ready ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 400 } }
        Image {
            id: wallImage
            anchors.fill: parent
            source: win.backdropOn ? "file://" + app.wallpaperPath.split("/").map(encodeURIComponent).join("/") : ""
            fillMode: Image.PreserveAspectCrop
            asynchronous: true
            smooth: true
        }
        Rectangle { anchors.fill: parent; color: Qt.alpha(theme.background, 0.78) }
    }

    // What pop-ups blur behind them (KDialog).
    readonly property Item blurTarget: mainArea
    RowLayout {
        id: mainArea
        anchors.fill: parent
        spacing: 0
        opacity: win.tv ? 0 : 1
        visible: opacity > 0 && win.contentShown
        Behavior on opacity { enabled: !app.light; NumberAnimation { duration: 280; easing.type: Easing.InOutQuad } }
        enabled: !win.tv

        // ---------------------------------------------------------------- sidebar
        Rectangle {
            id: sidebar
            Layout.fillHeight: true
            Layout.preferredWidth: 236
            color: win.backdropOn ? Qt.alpha(theme.surfaceContainerLow, 0.55) : theme.surfaceContainerLow
            // Lamplight: a warm glow pooling in the sidebar's bottom corner, like the icon.
            Rectangle {
                anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                height: parent.height * 0.45
                gradient: Gradient {
                    GradientStop { position: 0.0; color: "transparent" }
                    GradientStop { position: 1.0; color: Qt.alpha(theme.primary, 0.10) }
                }
            }

            // Always in view: TV mode and the tools, below the scrolling lists.
            ColumnLayout {
                id: sideBottom
                anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: 14 }
                spacing: 4
                Rectangle { Layout.fillWidth: true; height: 1; color: theme.outlineVariant; opacity: sideFlick.contentHeight > sideFlick.height + 1 ? 1 : 0 }
                NavItem { label: qsTr("TV mode"); icon: "tv"; count: "F11"; onPicked: win.tv = true }
                RowLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: 6
                    spacing: 1
                    ToolIcon { icon: "gamepad-2"; tip: qsTr("What should I play?"); onPicked: picker.show() }
                    ToolIcon { icon: "trophy"; tip: qsTr("Stats"); onPicked: statsBox.show() }
                    ToolIcon { icon: "folder-open"; tip: qsTr("Storage"); onPicked: storage.show() }
                    ToolIcon { icon: "check"; tip: healthBox.bad > 0 ? qsTr("Health check: ") + healthBox.bad + qsTr(" to fix") : qsTr("Health check")
                               alert: healthBox.bad > 0; onPicked: healthBox.show() }
                    ToolIcon { visible: app.hiddenCount > 0 || library.showHidden; icon: "eye-off"; on: library.showHidden
                               tip: qsTr("Hidden games (") + app.hiddenCount + ")"
                               onPicked: { library.storeFilter = ""; library.shelf = ""; library.showHidden = !library.showHidden } }
                    Item { Layout.fillWidth: true }
                    ToolIcon { icon: "user-round"; tip: qsTr("Accounts"); onPicked: accounts.open() }
                    ToolIcon { icon: "sliders-horizontal"; tip: qsTr("Settings"); onPicked: prefs.open() }
                }
            }

            // Scrolls when the list is taller than the window (a short screen, many collections);
            // otherwise the bottom items sit at the bottom as before.
            Flickable {
                id: sideFlick
                anchors { left: parent.left; right: parent.right; top: parent.top; bottom: sideBottom.top
                          leftMargin: 14; rightMargin: 14; topMargin: 14 }
                contentHeight: sideCol.height
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                interactive: contentHeight > height + 1
                ScrollBar.vertical: KScrollBar { visible: sideFlick.contentHeight > sideFlick.height + 1 }
            ColumnLayout {
                id: sideCol
                width: sideFlick.width
                height: Math.max(sideFlick.height, implicitHeight)
                spacing: 4

                RowLayout {
                    Layout.margins: 8
                    Layout.bottomMargin: 16
                    spacing: 10
                    WordMark { size: 20 }
                }
                // Who is playing: only shown once there is more than one person.
                Flow {
                    visible: app.profiles.length > 1
                    Layout.fillWidth: true
                    Layout.leftMargin: 8; Layout.bottomMargin: 10
                    spacing: 6
                    Repeater {
                        model: app.profiles
                        Rectangle {
                            required property string modelData
                            readonly property bool on: modelData === app.profile
                            height: 28; radius: 14
                            width: whoText.implicitWidth + 24
                            color: on ? theme.primary : "transparent"
                            border.width: on ? 0 : 1; border.color: theme.outlineVariant
                            Text { id: whoText; anchors.centerIn: parent; text: parent.modelData; font.pixelSize: 12; font.weight: Font.DemiBold
                                   color: parent.on ? theme.onPrimary : theme.onSurfaceVariant }
                            TapHandler { onTapped: app.switchProfile(parent.modelData) }
                            HoverHandler { cursorShape: Qt.PointingHandCursor }
                        }
                    }
                }

                component NavItem: Rectangle {
                    id: nav
                    readonly property var theme: app.theme
                    property string label
                    property string dot: ""
                    property string store: ""
                    property string icon: ""
                    property string count: ""
                    property bool active: false
                    property bool dim: false
                    property bool removable: false
                    signal picked()
                    signal remove()
                    Layout.fillWidth: true
                    height: 40
                    radius: 12
                    // Selected: a soft wash of the accent with a faint glow, not a solid block.
                    color: active ? Qt.alpha(theme.primary, 0.16) : navHover.hovered ? Qt.alpha(theme.surfaceContainerHigh, 0.9) : "transparent"
                    border.width: active ? 1 : 0
                    border.color: Qt.alpha(theme.primary, 0.28)
                    Behavior on color { enabled: !app.light; ColorAnimation { duration: 120 } }
                    RectangularShadow {
                        z: -1
                        anchors.fill: parent
                        visible: nav.active && !app.light && GraphicsInfo.api !== GraphicsInfo.Software
                        radius: parent.radius; blur: 18
                        color: Qt.alpha(theme.primary, 0.18)
                    }
                    // Accent bar on the selected item.
                    Rectangle {
                        visible: nav.active
                        x: 0; anchors.verticalCenter: parent.verticalCenter
                        width: 4; height: 20; radius: 2
                        color: theme.primary
                    }
                    StoreTile {
                        visible: nav.dot !== ""
                        x: 10; anchors.verticalCenter: parent.verticalCenter
                        anchors.verticalCenterOffset: navHover.hovered && !app.light ? -1 : 0
                        size: 22
                        store: nav.store
                        opacity: nav.dim ? 0.35 : 1
                        scale: navHover.hovered && !app.light ? 1.12 : 1
                        Behavior on scale { NumberAnimation { duration: 140; easing.type: Easing.OutBack } }
                        Behavior on anchors.verticalCenterOffset { NumberAnimation { duration: 140 } }
                    }
                    Icon {
                        visible: nav.dot === "" && nav.icon !== ""
                        x: 13; anchors.verticalCenter: parent.verticalCenter
                        name: nav.icon; size: 17
                        color: nav.active ? theme.primary : theme.onSurfaceVariant
                    }
                    Text {
                        x: nav.dot !== "" || nav.icon !== "" ? 38 : 14
                        anchors.verticalCenter: parent.verticalCenter
                        text: nav.label
                        color: theme.onSurface
                        opacity: nav.dim ? 0.6 : 1
                        font.pixelSize: 14
                        font.weight: nav.active ? Font.DemiBold : Font.Normal
                    }
                    Text {
                        anchors { right: parent.right; rightMargin: 14; verticalCenter: parent.verticalCenter }
                        visible: !(nav.removable && navHover.hovered) && (navHover.hovered || nav.active || nav.count === "…" || nav.count === "!")
                        text: nav.count
                        color: nav.active ? theme.primary : theme.onSurfaceVariant
                        font.pixelSize: 12
                    }
                    HoverHandler { id: navHover; cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: nav.picked() }
                    // Remove (collections): an x where the count was, while pointed at.
                    Rectangle {
                        visible: nav.removable && navHover.hovered
                        anchors { right: parent.right; rightMargin: 8; verticalCenter: parent.verticalCenter }
                        width: 24; height: 24; radius: 12
                        color: removeHover.hovered ? theme.errorContainer || theme.surfaceContainerHighest : "transparent"
                        Icon { anchors.centerIn: parent; name: "x"; size: 14; color: removeHover.hovered ? theme.error : theme.onSurfaceVariant }
                        HoverHandler { id: removeHover }
                        TapHandler { onTapped: nav.remove() }
                    }
                }

                NavItem {
                    label: qsTr("All games")
                    icon: "library"
                    count: app.totalCount
                    active: library.storeFilter === "" && !library.showHidden && library.shelf === ""
                    onPicked: { library.showHidden = false; library.storeFilter = ""; library.shelf = "" }
                }
                Repeater {
                    model: app.storesInfo
                    NavItem {
                        required property var modelData
                        visible: modelData.count > 0 || (modelData.inAccounts && modelData.loggedIn)
                        label: modelData.name
                        dot: modelData.color
                        store: modelData.id
                        dim: !modelData.loggedIn && modelData.count === 0
                        count: modelData.refreshing ? "…" : modelData.count
                        active: library.storeFilter === modelData.id && !library.showHidden && library.shelf === ""
                        onPicked: { library.showHidden = false; library.shelf = ""; library.storeFilter = modelData.id }
                    }
                }

                // Your lists: favourites, collections, and backlog statuses that have games.
                RowLayout {
                    // Shown once there is a list (make the first one from a game's More > Add to a collection).
                    visible: app.sidebarShelves.some(x => x.count > 0 || x.id !== "fav") || app.sidebarStatuses.length > 0
                    Layout.fillWidth: true
                    Layout.topMargin: 14; Layout.leftMargin: 14; Layout.rightMargin: 6; Layout.bottomMargin: 2
                    Text { Layout.fillWidth: true; text: qsTr("YOUR LISTS"); color: theme.outline; font.pixelSize: 11; font.weight: Font.DemiBold; font.letterSpacing: 1.2 }
                    Rectangle {
                        width: 24; height: 24; radius: 12
                        color: addHover.hovered ? theme.surfaceContainerHigh : "transparent"
                        Icon { anchors.centerIn: parent; name: "plus"; size: 15; color: theme.onSurfaceVariant }
                        HoverHandler { id: addHover; cursorShape: Qt.PointingHandCursor }
                        TapHandler { onTapped: newColl.ask("") }
                        ToolTip.visible: addHover.hovered; ToolTip.text: "New collection"; ToolTip.delay: 400
                    }
                }
                Repeater {
                    model: app.sidebarShelves
                    NavItem {
                        required property var modelData
                        // An empty Favourites stays out of the way until something is starred.
                        visible: modelData.id !== "fav" || modelData.count > 0 || active
                        label: modelData.name
                        icon: modelData.id === "fav" ? "star" : "bookmark"
                        count: modelData.count
                        removable: modelData.id !== "fav"
                        active: library.shelf === modelData.id && !library.showHidden
                        onPicked: { library.showHidden = false; library.storeFilter = ""; library.shelf = modelData.id }
                        onRemove: { removeColl.name = modelData.name; removeColl.open() }
                    }
                }
                Repeater {
                    model: app.sidebarStatuses
                    NavItem {
                        required property var modelData
                        label: modelData.name
                        icon: ({ "s:playing": "gamepad-2", "s:want": "clock", "s:finished": "check", "s:dropped": "x" })[modelData.id] || "bookmark"
                        count: modelData.count
                        active: library.shelf === modelData.id && !library.showHidden
                        onPicked: { library.showHidden = false; library.storeFilter = ""; library.shelf = modelData.id }
                    }
                }

                Item { Layout.fillHeight: true }
                // Tools: one row of icons (their names show on hover).
                component ToolIcon: Rectangle {
                    id: ti
                    property string icon
                    property string tip
                    property bool alert: false
                    property bool on: false
                    signal picked()
                    width: 28; height: 32; radius: 9
                    color: on ? theme.primaryContainer : tiHover.hovered ? theme.surfaceContainerHigh : "transparent"
                    Icon { anchors.centerIn: parent; name: ti.icon; size: 17; color: ti.on ? theme.onPrimaryContainer : theme.onSurfaceVariant }
                    Rectangle { visible: ti.alert; width: 8; height: 8; radius: 4; color: theme.error; anchors { right: parent.right; top: parent.top; margins: 4 } }
                    HoverHandler { id: tiHover; cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: ti.picked() }
                    ToolTip.visible: tiHover.hovered; ToolTip.text: ti.tip; ToolTip.delay: 300
                }

            }
            }
        }

        // ---------------------------------------------------------------- library
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            // Ambient light: the banner game's art, blurred and faint, behind the top of the page.
            // A zero-height item drawn first, so it sits under the toolbar and the grid.
            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: 0
                z: -1
                visible: !app.light && GraphicsInfo.api !== GraphicsInfo.Software && !!win.heroInfo.key
                Rectangle {  // over the wallpaper backdrop, the art fades out by transparency
                    id: ambientFade
                    width: parent.width; height: 620
                    visible: false
                    layer.enabled: true
                    gradient: Gradient {
                        GradientStop { position: 0.0; color: "white" }
                        GradientStop { position: 0.55; color: Qt.alpha("white", 0.6) }
                        GradientStop { position: 1.0; color: "transparent" }
                    }
                }
                Item {
                    width: parent.width
                    height: 620
                    clip: true  // the blur spreads past its box, under the fade that hides the bottom
                    layer.enabled: win.backdropOn
                    layer.effect: MultiEffect { maskEnabled: true; maskSource: ambientFade; maskThresholdMin: 0.5; maskSpreadAtMin: 1.0 }
                    ArtImage {
                        id: ambientArt
                        anchors.fill: parent
                        sources: win.heroInfo.heroes || win.heroInfo.covers || []
                        sourceSize.width: 480
                        visible: false
                    }
                    MultiEffect {
                        anchors.fill: parent
                        source: ambientArt
                        blurEnabled: true; blur: 1.0; blurMax: 64
                        saturation: 0.3
                        opacity: ambientArt.status === Image.Ready ? 0.32 : 0
                        Behavior on opacity { NumberAnimation { duration: 800 } }
                    }
                    Rectangle {
                        anchors.fill: parent
                        // Over the wallpaper backdrop it fades out instead of to the solid background.
                        gradient: Gradient {
                            GradientStop { position: 0.0; color: Qt.alpha(theme.background, 0.25) }
                            GradientStop { position: 1.0; color: win.backdropOn ? "transparent" : theme.background }
                        }
                    }
                }
            }

            RowLayout {
                Layout.margins: 20
                Layout.bottomMargin: 8
                spacing: 12
                KField {
                    id: search
                    theme: win.theme
                    Layout.fillWidth: true
                    Layout.maximumWidth: 460
                    iconName: "search"
                    placeholderText: qsTr("Search your games  (Ctrl+F)")
                    onTextChanged: library.search = text
                    Keys.onDownPressed: grid.forceActiveFocus()
                    Keys.onEscapePressed: { text = ""; grid.forceActiveFocus() }
                }
                // How many games, when it tells you something (a search, a filter, a store or a list).
                Text {
                    visible: !!library.search || (library.tags || []).length > 0 || library.installedOnly || !!library.storeFilter || !!library.shelf
                    text: grid.count + (grid.count === 1 ? qsTr(" game") : qsTr(" games"))
                    color: theme.onSurfaceVariant
                    font.pixelSize: 13
                }
                Item { Layout.fillWidth: true }
                // Filters: the chip row shows while this is on, or while a filter is set.
                TopButton {
                    icon: "filter"; label: qsTr("Filters")
                    badge: (library.tags || []).length
                    on: win.showFilters || (library.tags || []).length > 0
                    onPicked: win.showFilters = !win.showFilters
                }
                // View: covers or list, sort, installed only, cover size.
                TopButton {
                    id: viewButton
                    icon: (app.settingsMap.view || "grid") === "list" ? "list" : "layout-grid"; label: qsTr("View")
                    badge: library.installedOnly ? 1 : 0
                    onPicked: viewMenu.opened ? viewMenu.close() : viewMenu.open()
                    Popup {
                        id: viewMenu
                        y: parent.height + 6
                        x: parent.width - width
                        width: 270
                        padding: 14
                        background: Rectangle { radius: 14; color: theme.surfaceContainerHigh; border.width: 1; border.color: theme.outlineVariant }
                        contentItem: ColumnLayout {
                            spacing: 10
                            Text { text: qsTr("Show as"); color: theme.outline; font.pixelSize: 11; font.weight: Font.DemiBold }
                            RowLayout {
                                spacing: 6
                                Repeater {
                                    model: [{ v: "grid", i: "layout-grid", t: "Covers" }, { v: "list", i: "list", t: "List" }]
                                    Chip2 { required property var modelData; label: modelData.t; icon: modelData.i
                                            on: (app.settingsMap.view || "grid") === modelData.v; onPicked: app.setSetting("view", modelData.v) }
                                }
                            }
                            Text { text: qsTr("Sort by"); color: theme.outline; font.pixelSize: 11; font.weight: Font.DemiBold }
                            Flow {
                                Layout.fillWidth: true
                                spacing: 6
                                Repeater {
                                    model: [{ v: "name", t: "Name" }, { v: "recent", t: "Recently played" }, { v: "playtime", t: "Most played" },
                                            { v: "rating", t: "My rating" }, { v: "size", t: "Size" }]
                                    Chip2 { required property var modelData; label: modelData.t
                                            on: library.sortMode === modelData.v; onPicked: library.sortMode = modelData.v }
                                }
                            }
                            RowLayout {
                                Text { Layout.fillWidth: true; text: qsTr("Installed only"); color: theme.onSurface; font.pixelSize: 13 }
                                Switch { checked: library.installedOnly; onToggled: library.installedOnly = checked }
                            }
                            Text { visible: (app.settingsMap.view || "grid") !== "list"; text: qsTr("Cover size"); color: theme.outline; font.pixelSize: 11; font.weight: Font.DemiBold }
                            KSlider { visible: (app.settingsMap.view || "grid") !== "list"; theme: win.theme; Layout.fillWidth: true
                                      from: 130; to: 320; stepSize: 2; value: app.settingsMap.card_size
                                      onMoved: app.setSetting("card_size", value) }
                        }
                    }
                }
                KButton {
                    theme: win.theme
                    text: qsTr("Add")
                    iconName: "plus"
                    onClicked: addBox.show()
                }
                // Downloads: only while something downloads, waits or is paused.
                Rectangle {
                    visible: app.downloads.length > 0
                    width: 38; height: 38; radius: 19
                    color: dlHover.hovered || downloadsBox.opened ? theme.surfaceContainerHigh : "transparent"
                    Icon { anchors.centerIn: parent; name: "download"; size: 17; color: theme.primary }
                    Rectangle {
                        anchors { right: parent.right; top: parent.top; rightMargin: 2; topMargin: 2 }
                        width: Math.max(16, dlCount.implicitWidth + 8); height: 16; radius: 8
                        color: theme.primary
                        Text { id: dlCount; anchors.centerIn: parent; text: app.downloads.length; color: theme.onPrimary
                               font.pixelSize: 10; font.weight: Font.Bold }
                    }
                    HoverHandler { id: dlHover; cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: downloadsBox.open() }
                    ToolTip.visible: dlHover.hovered; ToolTip.text: qsTr("Downloads"); ToolTip.delay: 300
                }
                // Refresh: Cornerplay refreshes on its own at start and when you come back to it.
                Rectangle {
                    width: 38; height: 38; radius: 19
                    color: rfHover.hovered ? theme.surfaceContainerHigh : "transparent"
                    Icon {
                        id: rfIcon
                        anchors.centerIn: parent; name: "refresh-cw"; size: 17; color: theme.onSurfaceVariant
                        RotationAnimation on rotation { running: app.refreshing && !app.light; from: 0; to: 360; duration: 1100; loops: Animation.Infinite
                                                        onRunningChanged: if (!running) rfIcon.rotation = 0 }
                    }
                    HoverHandler { id: rfHover; cursorShape: Qt.PointingHandCursor }
                    TapHandler { enabled: !app.refreshing; onTapped: app.refresh("", true) }
                    ToolTip.visible: rfHover.hovered; ToolTip.text: app.refreshing ? "Refreshing…" : "Refresh (Ctrl+R)"; ToolTip.delay: 300
                }
            }

            // A hairline under the toolbar once the library has scrolled.
            Rectangle {
                Layout.fillWidth: true
                Layout.leftMargin: 20; Layout.rightMargin: 20
                Layout.preferredHeight: 1
                color: theme.outlineVariant
                opacity: grid.contentY > grid.originY + 4 ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: 200 } }
            }

            // Filter chips: pick several; a genre from the details fetched so far.
            Flow {
                id: chips
                visible: win.showFilters || (library.tags || []).length > 0
                Layout.fillWidth: true
                Layout.leftMargin: 20; Layout.rightMargin: 20; Layout.bottomMargin: 8
                spacing: 6
                property var genres: []
                Connections { target: app; function onDetailsGrew() { chips.genres = app.genreList().slice(0, 14) } }
                Component.onCompleted: genres = app.genreList().slice(0, 14)
                function toggle(tag) {
                    const t = (library.tags || []).slice()
                    const i = t.indexOf(tag)
                    if (i === -1) t.push(tag); else t.splice(i, 1)
                    library.tags = t
                }
                Repeater {
                    model: [{ t: "unplayed", l: "Never played", i: "sparkles" }, { t: "linux", l: "Linux version", i: "" },
                            { t: "controller", l: "Full controller support", i: "gamepad-2" }, { t: "protondb", l: "Runs well (ProtonDB Gold+)", i: "check" }]
                    Chip2 { required property var modelData; label: modelData.l; icon: modelData.i
                            on: (library.tags || []).indexOf(modelData.t) !== -1; onPicked: chips.toggle(modelData.t) }
                }
                Repeater {
                    model: chips.genres
                    Chip2 { required property string modelData; label: modelData
                            on: (library.tags || []).indexOf("genre:" + modelData) !== -1; onPicked: chips.toggle("genre:" + modelData) }
                }
                Chip2 { visible: (library.tags || []).length > 0; label: qsTr("Clear filters"); icon: "x"; onPicked: library.tags = [] }
            }
            Text {
                Layout.leftMargin: 22; Layout.bottomMargin: 6
                readonly property var free: library.search ? app.epicFree.filter(g => g.title.toLowerCase().indexOf(library.search) !== -1) : []
                visible: free.length > 0
                text: qsTr("Also free on Epic right now: ") + free.map(g => g.title).join(", ")
                color: theme.primary; font.pixelSize: 12
            }

            // A game started from Cornerplay is running: how long, and a way out when it hangs.
            Repeater {
                model: app.nowPlaying
                Rectangle {
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.leftMargin: 20; Layout.rightMargin: 20; Layout.bottomMargin: 8
                    height: 52; radius: 14
                    color: theme.surfaceContainerHigh
                    border.width: 1; border.color: theme.primary
                    property int now: Date.now() / 1000
                    Timer { interval: 15000; running: true; repeat: true; onTriggered: parent.now = Date.now() / 1000 }
                    RowLayout {
                        anchors { fill: parent; leftMargin: 16; rightMargin: 8 }
                        spacing: 10
                        Icon { name: "play"; size: 16; color: theme.primary }
                        Text {
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                            readonly property int mins: Math.max(0, Math.floor((parent.parent.now - modelData.since) / 60))
                            text: qsTr("Playing ") + modelData.title + "  ·  " + (mins >= 60 ? Math.floor(mins / 60) + " h " + (mins % 60) + qsTr(" min") : mins + qsTr(" min"))
                            color: theme.onSurface; font.pixelSize: 14; font.weight: Font.DemiBold
                        }
                        KButton { theme: win.theme; text: qsTr("Quit game"); iconName: "x"; onClicked: app.quitGame(modelData.key, false) }
                        KButton { theme: win.theme; danger: true; text: qsTr("Force close"); onClicked: app.quitGame(modelData.key, true) }
                    }
                }
            }

            // The Flatpak's first start on a PC where the regular install was used: offer to bring
            // its library, settings and sign-ins over (the sandbox cannot see them by itself).
            Rectangle {
                Layout.fillWidth: true
                Layout.leftMargin: 20; Layout.rightMargin: 20; Layout.bottomMargin: 8
                visible: !!app.hostImport.offer || !!app.hostImport.busy
                height: 52; radius: 14
                color: theme.primaryContainer
                RowLayout {
                    anchors { fill: parent; leftMargin: 16; rightMargin: 8 }
                    spacing: 10
                    Icon { name: "download"; size: 18; color: theme.onPrimaryContainer }
                    Text {
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                        text: app.hostImport.busy ? qsTr("Bringing over your library…")
                              : qsTr("Cornerplay is also installed outside Flatpak. Bring over its library, settings and sign-ins?")
                        color: theme.onPrimaryContainer; font.pixelSize: 14; font.weight: Font.DemiBold
                    }
                    KButton { theme: win.theme; primary: true; visible: !app.hostImport.busy; text: qsTr("Bring over")
                              iconName: "download"; onClicked: app.importFromHost() }
                    KButton { theme: win.theme; visible: !app.hostImport.busy; text: qsTr("Not now"); onClicked: app.dismissHostImport() }
                }
            }

            // A newer Cornerplay is out (installed copies only; checked once a day).
            Rectangle {
                Layout.fillWidth: true
                Layout.leftMargin: 20; Layout.rightMargin: 20; Layout.bottomMargin: 8
                visible: !!app.appUpdate.version
                height: 52; radius: 14
                color: theme.primaryContainer
                RowLayout {
                    anchors { fill: parent; leftMargin: 16; rightMargin: 8 }
                    spacing: 10
                    Icon { name: app.appUpdate.installed ? "check" : "gift"; size: 18; color: theme.onPrimaryContainer }
                    Text {
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                        text: app.appUpdate.installed ? qsTr("Cornerplay ") + app.appUpdate.version + qsTr(" is installed. Restart to use it.")
                              : app.appUpdate.busy ? "Updating to Cornerplay " + app.appUpdate.version + "…"
                              : "Cornerplay " + app.appUpdate.version + " is out."
                        color: theme.onPrimaryContainer; font.pixelSize: 14; font.weight: Font.DemiBold
                    }
                    KButton { theme: win.theme; visible: !app.appUpdate.installed && !app.appUpdate.busy; text: qsTr("What's new"); onClicked: app.openUrl(app.appUpdate.url) }
                    KButton { theme: win.theme; primary: true; visible: !app.appUpdate.busy
                              text: app.appUpdate.installed ? qsTr("Restart") : qsTr("Update")
                              iconName: app.appUpdate.installed ? "refresh-cw" : "download"
                              onClicked: app.appUpdate.installed ? app.restartApp() : app.installUpdate() }
                    KButton { theme: win.theme; visible: !app.appUpdate.busy; iconName: "x"; text: ""; onClicked: app.dismissUpdate() }
                }
            }

            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true

                // A soft glow in the colour of the game under the pointer.
                Rectangle {
                    id: glowRect
                    anchors.fill: parent
                    visible: !app.light
                    property color glow: win.hoverAccent || "transparent"
                    Behavior on glow { ColorAnimation { duration: 500 } }
                    gradient: Gradient {
                        GradientStop { position: 0.0; color: Qt.alpha(glowRect.glow, 0.10) }
                        GradientStop { position: 0.6; color: Qt.alpha(glowRect.glow, 0.03) }
                        GradientStop { position: 1.0; color: "transparent" }
                    }
                }
                // Changing store or list: the covers slide in and fade, rather than snapping.
                Connections {
                    target: library
                    function onFilterChanged() { if (!app.light && !library.search) gridSwap.restart() }
                }
                ParallelAnimation {
                    id: gridSwap
                    NumberAnimation { target: grid; property: "opacity"; from: 0.2; to: 1; duration: 260; easing.type: Easing.OutCubic }
                    NumberAnimation { target: gridSlide; property: "y"; from: 22; to: 0; duration: 300; easing.type: Easing.OutCubic }
                }
                GridView {
                    id: grid
                    objectName: "libraryGrid"
                    transform: Translate { id: gridSlide }
                    visible: (app.settingsMap.view || "grid") !== "list"
                    anchors.fill: parent
                    anchors.leftMargin: 12
                    anchors.rightMargin: 12
                    clip: true
                    focus: true
                    model: library
                    readonly property int columns: Math.max(2, Math.floor(width / app.settingsMap.card_size))
                    property int hoverIndex: -1
                    // Only show the keyboard selection once the keys (or a controller) are used.
                    property bool keyed: false
                    Keys.onPressed: (event) => { keyed = true; event.accepted = false }
                    cellWidth: Math.floor(width / columns)
                    cellHeight: Math.round(cellWidth * 1.46)
                    cacheBuffer: app.light ? 0 : cellHeight * 2
                    keyNavigationEnabled: true
                    // Follow the selection only when it moves (keys, controller). Following it always made
                    // a short window open scrolled past the banner to keep the first card in view.
                    highlightFollowsCurrentItem: false
                    onCurrentIndexChanged: {
                        if (!activeFocus) return
                        keyed = true
                        if (currentIndex <= 0) positionViewAtBeginning()
                        else positionViewAtIndex(currentIndex, GridView.Contain)
                    }
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: KScrollBar { }
                    populate: Transition {
                        enabled: !app.light
                        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 320; easing.type: Easing.OutCubic }
                        NumberAnimation { property: "y"; from: ViewTransition.destination.y + 24; duration: 360; easing.type: Easing.OutCubic }
                    }
                    // Filters and searches: covers fade in and slide to their new places.
                    add: Transition {
                        enabled: !app.light
                        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 220 }
                        NumberAnimation { property: "scale"; from: 0.92; to: 1; duration: 220; easing.type: Easing.OutCubic }
                    }
                    displaced: Transition {
                        enabled: !app.light
                        NumberAnimation { properties: "x,y"; duration: 240; easing.type: Easing.OutCubic }
                    }
                    // Hero banner for the last game you played, then the rest of "Continue playing".
                    // Part of the grid's header, so it scrolls away with the library.
                    header: Column {
                        width: grid.width
                        readonly property bool shown: app.recentGames.length > 0 && !library.search
                                                      && !library.storeFilter && !library.showHidden && !library.shelf
                        visible: shown
                        height: shown ? implicitHeight : 0
                        // The banner fills in after the grid; stay at the top instead of keeping game 1 in place.
                        onHeightChanged: if (grid.currentIndex <= 0) Qt.callLater(grid.positionViewAtBeginning)
                        topPadding: 4
                        bottomPadding: 20
                        spacing: 24

                        // The banner folded away: one slim line to bring it back.
                        RowLayout {
                            visible: win.homeFolded("banner")
                            x: 8; width: parent.width - 16
                            Text { text: qsTr("Back in your corner: ") + (win.heroInfo.title || ""); color: theme.onSurfaceVariant; font.pixelSize: 13; font.weight: Font.DemiBold; elide: Text.ElideRight; Layout.fillWidth: true }
                            Icon { name: "chevron-down"; size: 16; color: theme.onSurfaceVariant
                                   TapHandler { onTapped: win.toggleHome("banner") }
                                   HoverHandler { cursorShape: Qt.PointingHandCursor } }
                        }
                        Item {
                            id: hero
                            visible: !win.homeFolded("banner")
                            property var info: win.heroInfo
                            property var game: info.key ? app.game(info.key) : ({})
                            property string accent: info.key ? app.gameColour(info.key) : ""
                            readonly property var tint: win.tinted(accent)
                            onInfoChanged: { accent = info.key ? app.gameColour(info.key) : ""; heroFade.restart() }
                            // Cross-fade to the next game.
                            ParallelAnimation {
                                id: heroFade
                                NumberAnimation { target: heroArt; property: "opacity"; from: app.light ? 1 : 0.15; to: 1; duration: 600; easing.type: Easing.OutCubic }
                                NumberAnimation { target: heroContent; property: "opacity"; from: app.light ? 1 : 0; to: 1; duration: 450; easing.type: Easing.OutCubic }
                            }
                            HoverHandler { onHoveredChanged: win.heroPaused = hovered }
                            Connections {
                                target: app
                                function onGameChanged(key) { if (!key || key === hero.info.key) hero.game = app.game(hero.info.key) }
                                function onGameColourReady(key, colour) { if (key === hero.info.key) hero.accent = colour }
                            }
                            x: 8
                            width: parent.width - 16
                            height: Math.round(Math.min(340, Math.max(250, width * 0.28)))

                            Item {
                                id: heroArt
                                anchors.fill: parent
                                layer.enabled: GraphicsInfo.api !== GraphicsInfo.Software
                                layer.effect: MultiEffect { maskEnabled: true; maskSource: heroMask; maskThresholdMin: 0.5; maskSpreadAtMin: 1.0 }

                                Rectangle { anchors.fill: parent; color: theme.surfaceContainerHigh }
                                // No wide art: the cover, blurred, fills the banner.
                                ArtImage {
                                    id: heroCover
                                    anchors.fill: parent
                                    sources: heroWide.status === Image.Ready ? [] : (hero.info.covers || [])
                                    sourceSize.width: 320
                                    visible: app.light && status === Image.Ready
                                    opacity: 0.45
                                }
                                MultiEffect {
                                    anchors.fill: parent
                                    source: heroCover
                                    visible: !app.light && heroCover.status === Image.Ready && heroWide.status !== Image.Ready
                                    blurEnabled: true; blur: 1.0; blurMax: 64
                                    saturation: 0.2
                                    opacity: 0.7
                                }
                                ArtImage {
                                    id: heroWide
                                    anchors.fill: parent
                                    sources: hero.info.heroes || []
                                    horizontalAlignment: Image.AlignRight
                                    sourceSize.width: Math.min(3840, Math.max(640, Math.ceil(width * Screen.devicePixelRatio / 40) * 40))
                                    opacity: status === Image.Ready ? 1 : 0
                                    Behavior on opacity { enabled: !app.light; NumberAnimation { duration: 350 } }
                                }
                                // Shade the left side so the text always reads, whatever the art.
                                Rectangle {
                                    anchors.fill: parent
                                    gradient: Gradient {
                                        orientation: Gradient.Horizontal
                                        GradientStop { position: 0.0; color: Qt.alpha(theme.background, 0.94) }
                                        GradientStop { position: 0.45; color: Qt.alpha(theme.background, 0.72) }
                                        GradientStop { position: 0.8; color: Qt.alpha(theme.background, 0.08) }
                                    }
                                }
                                Rectangle {
                                    anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                                    height: parent.height * 0.4
                                    gradient: Gradient {
                                        GradientStop { position: 0; color: "transparent" }
                                        GradientStop { position: 1; color: Qt.alpha(theme.background, 0.55) }
                                    }
                                }
                            }
                            Rectangle { id: heroMask; anchors.fill: parent; radius: 18; layer.enabled: true; visible: false }
                            Rectangle {  // fold the banner away
                                z: 2  // above the cover, which starts close to this corner
                                anchors { left: parent.left; top: parent.top; margins: 12 }
                                width: 28; height: 28; radius: 14
                                color: Qt.alpha("black", foldHover.hovered ? 0.6 : 0.35)
                                opacity: heroHover.hovered ? 1 : 0
                                Behavior on opacity { NumberAnimation { duration: 150 } }
                                Icon { anchors.centerIn: parent; name: "chevron-up"; size: 16; color: "white" }
                                HoverHandler { id: foldHover; cursorShape: Qt.PointingHandCursor }
                                TapHandler { onTapped: win.toggleHome("banner") }
                            }
                            HoverHandler { id: heroHover }
                            // Corner brackets, the icon's corner, framing the banner.
                            CornerMark { anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 18; rotation: 180; tone: hero.tint.primary; opacity: 0.6; size: 26; thick: 3.5 }
                            CornerMark { anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.margins: 18; rotation: -90; tone: hero.tint.primary; opacity: 0.6; size: 26; thick: 3.5 }
                            Rectangle {
                                anchors.fill: parent; radius: 18; color: "transparent"
                                border.width: 1; border.color: theme.dark === false ? Qt.alpha("black", 0.08) : Qt.alpha("white", 0.07)
                            }
                            // Dots: which of the recent games is showing; click one to jump to it.
                            Row {
                                visible: win.heroCount > 1
                                anchors { right: parent.right; bottom: parent.bottom; rightMargin: 60; bottomMargin: 18 }
                                spacing: 6
                                Repeater {
                                    model: win.heroCount
                                    Rectangle {
                                        required property int index
                                        readonly property bool on: index === win.heroAt % win.heroCount
                                        width: on ? 22 : 8; height: 8; radius: 4
                                        color: on ? hero.tint.primary : Qt.alpha("white", 0.45)
                                        Behavior on width { enabled: !app.light; NumberAnimation { duration: 200 } }
                                        TapHandler { enabled: win.cardsLive; onTapped: win.heroAt = parent.index }
                                        HoverHandler { cursorShape: Qt.PointingHandCursor }
                                    }
                                }
                            }

                            Row {
                                id: heroContent
                                anchors { left: parent.left; leftMargin: 28; verticalCenter: parent.verticalCenter }
                                spacing: 26
                                Item {
                                    id: heroThumbBox
                                    width: heroThumb.width; height: heroThumb.height
                                    visible: hero.width >= 620
                                    RectangularShadow {
                                        anchors.fill: parent
                                        visible: !app.light
                                        radius: heroThumb.radius
                                        blur: 28; offset.y: 12
                                        color: Qt.alpha("black", 0.55)
                                    }
                                Rectangle {
                                    id: heroThumb
                                    width: Math.round(hero.height * 0.62); height: Math.round(width * 1.46)
                                    radius: 12
                                    color: theme.surfaceContainerHighest
                                    border.width: 1; border.color: Qt.alpha("white", 0.12)
                                    anchors.verticalCenter: parent.verticalCenter
                                    RoundedArt {
                                        anchors.fill: parent; anchors.margins: 1
                                        radius: heroThumb.radius - 1
                                        ArtImage {
                                            anchors.fill: parent
                                            sources: hero.info.covers || []
                                            sourceSize.width: Math.min(300, Math.max(120, Math.ceil(width * Screen.devicePixelRatio / 40) * 40))
                                        }
                                    }
                                    Rectangle {  // the frame, over the cover's edge
                                        anchors.fill: parent; radius: heroThumb.radius; color: "transparent"
                                        border.width: 1; border.color: Qt.alpha("white", 0.12)
                                    }
                                }
                                }
                                Column {
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: Math.min(560, hero.width - (heroThumbBox.visible ? heroThumb.width + 26 : 0) - 56)
                                    spacing: 10
                                    Text {
                                        text: qsTr("BACK IN YOUR CORNER")
                                        color: hero.tint.primary
                                        font.pixelSize: 12; font.weight: Font.Bold; font.letterSpacing: 2
                                    }
                                    LogoTitle {
                                        logos: hero.info.logos || []
                                        title: hero.info.title || ""
                                        color: theme.onSurface
                                        pixelSize: hero.height > 290 ? 38 : 32
                                        logoHeight: Math.round(hero.height * 0.3)
                                        maxWidth: parent.width
                                    }
                                    Row {
                                        spacing: 8
                                        Rectangle {
                                            height: 24; radius: 12
                                            width: heroStore.implicitWidth + 37
                                            color: Qt.alpha(theme.surfaceContainerHighest, 0.85)
                                            StoreIcon { x: 8; anchors.verticalCenter: parent.verticalCenter; size: 14; store: hero.info.store || ""; color: hero.info.storeColor || "gray" }
                                            Text { id: heroStore; x: 27; anchors.verticalCenter: parent.verticalCenter; text: hero.info.storeName || ""; color: theme.onSurface; font.pixelSize: 12 }
                                        }
                                        Text {
                                            anchors.verticalCenter: parent.verticalCenter
                                            text: app.playedText(hero.game.playtime, hero.game.lastPlayed)
                                            color: theme.onSurfaceVariant
                                            font.pixelSize: 13
                                        }
                                    }
                                    Item { width: 1; height: 6 }
                                    Row {
                                        spacing: 10
                                        KButton {
                                            theme: hero.tint
                                            primary: true
                                            visible: !hero.game.job
                                            // Played on another PC (or uninstalled since): install it from here.
                                            text: hero.game.installed ? qsTr("Resume") : qsTr("Install")
                                            iconName: hero.game.installed ? "play" : "download"
                                            onClicked: {
                                                if (hero.game.installed) win.activate(hero.info.key)
                                                else { app.preferCopy(hero.info.key); app.install(hero.info.key) }
                                            }
                                        }
                                        KButton {
                                            theme: hero.tint
                                            visible: !hero.game.job && !!hero.game.update
                                            text: qsTr("Update")
                                            iconName: "arrow-up"
                                            onClicked: app.update(hero.info.key)
                                        }
                                        Text {
                                            visible: !!hero.game.job
                                            anchors.verticalCenter: parent.verticalCenter
                                            text: hero.game.job === "update" ? qsTr("Updating ") + Math.max(0, Math.floor(hero.game.progress)) + "%" : qsTr("Working…")
                                            color: theme.primary
                                            font.pixelSize: 14; font.weight: Font.DemiBold
                                        }
                                        KButton {
                                            theme: hero.tint
                                            text: qsTr("Details")
                                            onClicked: win.select(hero.info.key)
                                        }
                                    }
                                }
                            }
                        }

                        // The two sections sit in these slots, in the order the user chose.
                        readonly property bool continueFirst: (app.settingsMap.home_order || ["continue"])[0] === "continue"
                        readonly property bool continueShown: app.recentGames.length > 1
                        readonly property bool freeShown: app.epicFree.length > 0
                        Item { id: homeSlotA; width: parent.width; height: childrenRect.height
                               visible: parent.continueFirst ? parent.continueShown : parent.freeShown }
                        Item { id: homeSlotB; width: parent.width; height: childrenRect.height
                               visible: parent.continueFirst ? parent.freeShown : parent.continueShown }
                        Column {
                            parent: (app.settingsMap.home_order || ["continue"])[0] === "continue" ? homeSlotA : homeSlotB
                            visible: app.recentGames.length > 1
                            x: 8
                            width: parent.width - 16
                            spacing: 10
                            SectionHead { sid: "continue"; title: qsTr("Continue playing") }
                            ListView {
                                id: recentRow
                                visible: !win.homeFolded("continue")
                                width: parent.width
                                height: 132
                                orientation: ListView.Horizontal
                                spacing: 14
                                clip: true
                                boundsBehavior: Flickable.StopAtBounds
                                model: app.recentGames.slice(1)
                            delegate: Rectangle {
                                id: recentTile
                                required property var modelData
                                width: 300; height: 132
                                radius: 14
                                color: theme.surfaceContainerHigh
                                scale: recentHover.hovered && !app.light ? 1.02 : 1
                                Behavior on scale { enabled: !app.light; NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
                                // The cover takes the tile's left corners; the border is drawn over it.
                                RoundedArt {
                                    anchors.fill: parent
                                    radius: recentTile.radius
                                    // The game's wide art, faded in behind the text.
                                    ArtImage {
                                        id: recentWide
                                        visible: !app.light
                                        anchors.fill: parent
                                        sources: recentTile.modelData.heroes || []
                                        horizontalAlignment: Image.AlignRight
                                        sourceSize.width: 600
                                        opacity: status === Image.Ready ? (recentHover.hovered ? 0.55 : 0.4) : 0
                                        Behavior on opacity { NumberAnimation { duration: 220 } }
                                    }
                                    Rectangle {
                                        anchors.fill: parent
                                        visible: recentWide.visible && recentWide.status === Image.Ready
                                        gradient: Gradient {
                                            orientation: Gradient.Horizontal
                                            GradientStop { position: 0.25; color: theme.surfaceContainerHigh }
                                            GradientStop { position: 0.75; color: Qt.alpha(theme.surfaceContainerHigh, 0.55) }
                                            GradientStop { position: 1.0; color: Qt.alpha(theme.surfaceContainerHigh, 0.15) }
                                        }
                                    }
                                    ArtImage {
                                        width: 88; height: parent.height
                                        sources: recentTile.modelData.covers || []
                                        sourceSize.width: 176
                                    }
                                }
                                Rectangle {
                                    anchors.fill: parent; radius: recentTile.radius; color: "transparent"; z: 1
                                    border.width: recentHover.hovered ? 2 : 1
                                    border.color: recentHover.hovered ? theme.primary
                                                  : theme.dark === false ? Qt.alpha("black", 0.08) : Qt.alpha("white", 0.07)
                                }
                                Column {
                                    anchors { left: parent.left; leftMargin: 88 + 16; right: parent.right; rightMargin: 14; verticalCenter: parent.verticalCenter }
                                    spacing: 6
                                    Text {
                                        width: parent.width
                                        text: recentTile.modelData.title
                                        color: theme.onSurface
                                        font.pixelSize: 15; font.weight: Font.DemiBold
                                        wrapMode: Text.WordWrap; maximumLineCount: 2; elide: Text.ElideRight
                                    }
                                    Row {
                                        spacing: 6
                                        StoreTile { size: 16; store: recentTile.modelData.store; anchors.verticalCenter: parent.verticalCenter }
                                        Text { text: recentTile.modelData.storeName; color: theme.onSurfaceVariant; font.pixelSize: 12 }
                                    }
                                    Text {
                                        width: parent.width
                                        text: {
                                            const s = app.playedText(0, recentTile.modelData.lastPlayed).replace("Last played ", "")
                                            return s.charAt(0).toUpperCase() + s.slice(1)
                                        }
                                        color: theme.outline
                                        font.pixelSize: 12
                                        elide: Text.ElideRight
                                    }
                                }
                                HoverHandler { id: recentHover; enabled: win.cardsLive; cursorShape: Qt.PointingHandCursor }
                                TapHandler {
                                    enabled: win.cardsLive
                                    onSingleTapped: if (win.cardsLive) win.select(recentTile.modelData.key)
                                    onDoubleTapped: if (win.cardsLive) win.activate(recentTile.modelData.key)
                                    onLongPressed: if (win.cardsLive) gameMenu.showFor(recentTile.modelData.key, recentTile, point.position)
                                }
                                TapHandler {
                                    enabled: win.cardsLive
                                    acceptedButtons: Qt.RightButton
                                    onTapped: (eventPoint, button) => gameMenu.showFor(recentTile.modelData.key, recentTile, eventPoint.position)
                                }
                            }
                            }
                        }

                        // Epic's free games this week (and next): Get opens the store page.
                        Column {
                            parent: (app.settingsMap.home_order || ["continue"])[0] === "continue" ? homeSlotB : homeSlotA
                            visible: app.epicFree.length > 0
                            x: 8
                            width: parent.width - 16
                            spacing: 10
                            bottomPadding: 18
                            SectionHead {
                                sid: "free"; icon: "gift"
                                readonly property int nowFree: app.epicFree.filter(g => g.now && !g.owned).length
                                title: qsTr("Free on Epic") + (nowFree ? "  \u00B7  " + nowFree + qsTr(" this week") : "")
                                extra: qsTr("Hide until next week")
                                onExtraPicked: app.hideEpicFreeForNow()
                            }
                            ListView {
                                visible: !win.homeFolded("free")
                                width: parent.width
                                height: 132
                                orientation: ListView.Horizontal
                                spacing: 12
                                clip: true
                                boundsBehavior: Flickable.StopAtBounds
                                model: app.epicFree
                                delegate: Rectangle {
                                    id: freeTile
                                    required property var modelData
                                    width: 300; height: 132
                                    radius: 12
                                    color: theme.surfaceContainerHigh
                                    RoundedArt {
                                        anchors.fill: parent
                                        radius: freeTile.radius
                                        ArtImage {
                                            width: 94; height: parent.height
                                            sources: [freeTile.modelData.tall, freeTile.modelData.wide].filter(u => !!u)
                                            sourceSize.width: 188
                                        }
                                    }
                                    Rectangle {
                                        anchors.fill: parent; radius: freeTile.radius; color: "transparent"; z: 1
                                        border.width: freeHover.hovered ? 2 : 0
                                        border.color: freeHover.hovered ? theme.primary : theme.outlineVariant
                                    }
                                    Column {
                                        anchors { left: parent.left; leftMargin: 94 + 12; right: parent.right; rightMargin: 12; verticalCenter: parent.verticalCenter }
                                        spacing: 6
                                        Text {
                                            width: parent.width
                                            text: freeTile.modelData.title
                                            color: theme.onSurface
                                            font.pixelSize: 14; font.weight: Font.DemiBold
                                            wrapMode: Text.WordWrap; maximumLineCount: 2; elide: Text.ElideRight
                                        }
                                        Text {
                                            width: parent.width
                                            text: freeTile.modelData.now ? qsTr("Free until ") + freeTile.modelData.when
                                                                         : "Free from " + freeTile.modelData.when
                                            color: freeTile.modelData.now ? theme.primary : theme.outline
                                            font.pixelSize: 12
                                        }
                                        KButton {
                                            theme: win.theme
                                            visible: freeTile.modelData.now
                                            primary: !freeTile.modelData.owned
                                            enabled: !freeTile.modelData.owned
                                            text: freeTile.modelData.owned ? qsTr("In your library") : qsTr("Get")
                                            iconName: freeTile.modelData.owned ? "check" : "external-link"
                                            onClicked: app.openUrl(freeTile.modelData.url)
                                        }
                                    }
                                    HoverHandler { id: freeHover; cursorShape: Qt.PointingHandCursor }
                                }
                            }
                        }

                        // Games on your Steam / GOG wishlist that are on sale right now.
                        Column {
                            visible: app.wishlistSales.length > 0 && !library.search
                            x: 8
                            width: parent.width - 16
                            spacing: 10
                            bottomPadding: 18
                            SectionHead {
                                sid: "sales"; icon: "tag"
                                title: qsTr("On sale from your wishlist  \u00B7  ") + app.wishlistSales.length
                            }
                            ListView {
                                visible: !win.homeFolded("sales")
                                width: parent.width
                                height: 132
                                orientation: ListView.Horizontal
                                spacing: 12
                                clip: true
                                boundsBehavior: Flickable.StopAtBounds
                                model: app.wishlistSales
                                delegate: Rectangle {
                                    id: saleTile
                                    required property var modelData
                                    // IsThereAnyDeal's cheapest deal, when it is deeper than the wishlist store's own sale.
                                    readonly property var best: modelData.best && modelData.best.cut > (modelData.discount || 0) ? modelData.best : null
                                    width: 300; height: 132
                                    radius: 12
                                    color: theme.surfaceContainerHigh
                                    RoundedArt {
                                        anchors.fill: parent
                                        radius: saleTile.radius
                                        ArtImage {
                                            width: 94; height: parent.height
                                            sources: [saleTile.modelData.tall, saleTile.modelData.wide].filter(u => !!u)
                                            sourceSize.width: 188
                                        }
                                    }
                                    Rectangle {
                                        anchors.fill: parent; radius: saleTile.radius; color: "transparent"; z: 1
                                        border.width: saleHover.hovered ? 2 : 0
                                        border.color: theme.primary
                                    }
                                    Column {
                                        anchors { left: parent.left; leftMargin: 94 + 12; right: parent.right; rightMargin: 12; verticalCenter: parent.verticalCenter }
                                        spacing: 6
                                        Text {
                                            width: parent.width
                                            text: saleTile.modelData.title
                                            textFormat: Text.PlainText
                                            color: theme.onSurface
                                            font.pixelSize: 14; font.weight: Font.DemiBold
                                            wrapMode: Text.WordWrap; maximumLineCount: 2; elide: Text.ElideRight
                                        }
                                        Row {
                                            spacing: 8
                                            Rectangle {
                                                width: pct.implicitWidth + 12; height: 20; radius: 6
                                                color: theme.primary
                                                Text { id: pct; anchors.centerIn: parent; text: "-" + (saleTile.best ? saleTile.best.cut : saleTile.modelData.discount) + "%"
                                                       color: theme.onPrimary; font.pixelSize: 11; font.weight: Font.Bold }
                                            }
                                            Text { anchors.verticalCenter: parent.verticalCenter; text: saleTile.best ? saleTile.best.price : saleTile.modelData.price
                                                   textFormat: Text.PlainText; color: theme.onSurface; font.pixelSize: 13 }
                                            Text { anchors.verticalCenter: parent.verticalCenter; text: saleTile.best ? saleTile.best.was : saleTile.modelData.was
                                                   textFormat: Text.PlainText; color: theme.outline; font.pixelSize: 11; font.strikeout: true }
                                        }
                                        Text {
                                            visible: !!(saleTile.best && saleTile.best.low)
                                            text: qsTr("Lowest price ever")
                                            color: theme.primary; font.pixelSize: 11; font.weight: Font.DemiBold
                                        }
                                        KButton {
                                            theme: win.theme
                                            width: Math.min(implicitWidth, parent.width)
                                            text: saleTile.best ? saleTile.best.shop
                                                  : saleTile.modelData.store === "gog" ? qsTr("Open on GOG") : qsTr("Open on Steam")
                                            iconName: "external-link"
                                            onClicked: app.openUrl(saleTile.best ? saleTile.best.url : saleTile.modelData.url)
                                        }
                                    }
                                    HoverHandler { id: saleHover; cursorShape: Qt.PointingHandCursor }
                                }
                            }
                        }

                        Text {
                            x: 8
                            textFormat: Text.StyledText
                            text: (library.shelf === "" ? qsTr("Library") + qsTr("  <font color='") + theme.outline + "'>\u00B7  " + grid.count + qsTr(" games</font>")
                                  : library.shelf === "fav" ? "Favourites"
                                  : library.shelf.startsWith("s:") ? ((app.statusNames.find(s => "s:" + s.id === library.shelf) || {}).name || "")
                                  : library.shelf.replace(/^c:/, ""))
                            color: theme.onSurface
                            font.pixelSize: 15; font.weight: Font.DemiBold
                        }
                    }
                    delegate: GameCard {
                        id: gridCard
                        width: grid.cellWidth
                        height: grid.cellHeight
                        theme: win.theme
                        cornerRadius: app.settingsMap.card_radius
                        showBadge: app.settingsMap.show_badges
                        showProtonDb: app.settingsMap.show_protondb
                        showTitle: app.settingsMap.show_titles
                        dim: app.settingsMap.dim_uninstalled
                        // One highlight at a time: while the pointer is over a card, the keyboard
                        // selection steps back.
                        interactive: win.cardsLive
                        current: GridView.isCurrentItem && grid.activeFocus && grid.keyed && grid.hoverIndex < 0
                        trailer: win.trailerKey === key ? win.trailerUrl : ""
                        onHoveredChanged: {
                            grid.hoverIndex = hovered ? index : (grid.hoverIndex === index ? -1 : grid.hoverIndex)
                            if (hovered) { win.hoverKey = key; win.hoverAccent = app.gameColour(key); previewTimer.restart() }
                            else if (win.hoverKey === key) { previewTimer.stop(); preview.visible = false
                                                             trailerWait.stop(); win.trailerKey = ""; win.trailerUrl = "" }
                        }
                        onOpened: { grid.currentIndex = index; flyer.from(key, gridCard); win.select(key) }
                        onActivated: { grid.currentIndex = index; win.activate(key) }
                        onMenuRequested: at => { grid.currentIndex = index; gameMenu.showFor(key, gridCard, at) }
                        required property int index
                    }
                    Keys.onReturnPressed: {
                        const key = library.keyAt(currentIndex)
                        if (key) win.activate(key)
                    }
                    Keys.onSpacePressed: { const key = library.keyAt(currentIndex); if (key) win.select(key) }
                }

                // The library as a table: click a column to sort by it.
                ListView {
                    id: table
                    visible: (app.settingsMap.view || "grid") === "list"
                    anchors.fill: parent
                    anchors.leftMargin: 20; anchors.rightMargin: 20
                    clip: true
                    model: visible ? library : null
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: KScrollBar { }
                    readonly property var cols: [{ t: "Game", s: "name", w: 0 }, { t: "Store", s: "", w: 140 }, { t: "Status", s: "", w: 120 },
                                                 { t: "Rating", s: "rating", w: 96 }, { t: "Played", s: "playtime", w: 90 },
                                                 { t: "Last played", s: "recent", w: 110 }, { t: "Size", s: "size", w: 84 }]
                    headerPositioning: ListView.OverlayHeader
                    header: Rectangle {
                        width: table.width; height: 38; z: 2
                        color: theme.background
                        Row {
                            anchors.fill: parent
                            Repeater {
                                model: table.cols
                                Item {
                                    required property var modelData
                                    required property int index
                                    width: modelData.w || (table.width - 640 - 56)
                                    height: 38
                                    x: 0
                                    Text {
                                        anchors { left: parent.left; leftMargin: index === 0 ? 56 : 0; verticalCenter: parent.verticalCenter }
                                        text: modelData.t + (modelData.s && library.sortMode === modelData.s ? qsTr("  \u25BE") : "")
                                        color: modelData.s && library.sortMode === modelData.s ? theme.primary : theme.outline
                                        font.pixelSize: 12; font.weight: Font.DemiBold
                                    }
                                    HoverHandler { enabled: !!modelData.s; cursorShape: Qt.PointingHandCursor }
                                    TapHandler { enabled: !!modelData.s; onTapped: library.sortMode = modelData.s }
                                }
                            }
                        }
                        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: theme.outlineVariant }
                    }
                    delegate: Rectangle {
                        id: trow
                        required property int index
                        required property string key
                        required property string title
                        required property string storeName
                        required property string store
                        required property string storeColor
                        required property var covers
                        required property bool installed
                        required property string status
                        required property int rating
                        required property real playtime
                        required property real lastPlayed
                        required property real sizeBytes
                        width: table.width; height: 56
                        radius: 10
                        color: rowHover.hovered ? theme.surfaceContainerHigh : index % 2 ? Qt.alpha(theme.surfaceContainerLow, 0.6) : "transparent"
                        opacity: installed || !app.settingsMap.dim_uninstalled ? 1 : 0.65
                        Row {
                            anchors.fill: parent
                            Item {
                                width: table.width - 640 - 56 + 56; height: parent.height
                                RoundedArt { x: 8; anchors.verticalCenter: parent.verticalCenter; width: 30; height: 44; radius: 5
                                             ArtImage { anchors.fill: parent; sources: trow.covers || []; sourceSize.width: 60 } }
                                Text { x: 56; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 64
                                       text: trow.title; color: theme.onSurface; font.pixelSize: 14; elide: Text.ElideRight }
                            }
                            Row {
                                width: 140; height: parent.height; spacing: 6
                                StoreTile { anchors.verticalCenter: parent.verticalCenter; size: 18; store: trow.store }
                                Text { anchors.verticalCenter: parent.verticalCenter; text: trow.storeName; color: theme.onSurfaceVariant; font.pixelSize: 12 }
                            }
                            Text { width: 120; anchors.verticalCenter: parent.verticalCenter; font.pixelSize: 12; color: theme.onSurfaceVariant
                                   text: ({ playing: qsTr("Playing"), want: qsTr("Want to play"), finished: qsTr("Finished"), dropped: qsTr("Dropped") })[trow.status] || (trow.installed ? qsTr("Installed") : "") }
                            Text { width: 96; anchors.verticalCenter: parent.verticalCenter; font.pixelSize: 13; color: "#ffd166"
                                   text: trow.rating ? "\u2605".repeat(trow.rating) : "" }
                            Text { width: 90; anchors.verticalCenter: parent.verticalCenter; font.pixelSize: 12; color: theme.onSurfaceVariant
                                   text: trow.playtime >= 3600 ? Math.round(trow.playtime / 360) / 10 + " h" : trow.playtime > 0 ? Math.round(trow.playtime / 60) + qsTr(" min") : "" }
                            Text { width: 110; anchors.verticalCenter: parent.verticalCenter; font.pixelSize: 12; color: theme.onSurfaceVariant
                                   text: trow.lastPlayed > 0 ? new Date(trow.lastPlayed * 1000).toLocaleDateString(Qt.locale(), "d MMM yyyy") : "" }
                            Text { width: 84; anchors.verticalCenter: parent.verticalCenter; font.pixelSize: 12; color: theme.onSurfaceVariant
                                   text: trow.sizeBytes > 0 ? (trow.sizeBytes / 1073741824).toFixed(1) + qsTr(" GB") : "" }
                        }
                        HoverHandler { id: rowHover; cursorShape: Qt.PointingHandCursor }
                        TapHandler {
                            onSingleTapped: win.select(trow.key)
                            onDoubleTapped: win.activate(trow.key)
                            onLongPressed: gameMenu.showFor(trow.key, trow, point.position)
                        }
                        TapHandler {
                            acceptedButtons: Qt.RightButton
                            onTapped: (eventPoint, button) => gameMenu.showFor(trow.key, trow, eventPoint.position)
                        }
                    }
                }

                // Empty state: says why, and offers the way back.
                Column {
                    visible: grid.count === 0
                    anchors.centerIn: parent
                    spacing: 14
                    width: Math.min(parent.width - 60, 460)
                    EmptyScene {  // a little scene for the reason, in the theme's colours
                        visible: !app.refreshing
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: 240; height: 160
                        theme: win.theme
                        kind: app.totalCount === 0 ? "library"
                              : library.shelf && !library.search && !(library.tags || []).length ? "list" : "search"
                    }
                    Text {
                        width: parent.width
                        horizontalAlignment: Text.AlignHCenter
                        color: theme.onSurface
                        font.pixelSize: 20
                        font.weight: Font.DemiBold
                        text: library.showHidden ? qsTr("No hidden games")
                              : app.refreshing ? "Loading your libraries…"
                              : app.totalCount === 0 ? "Your corner is empty" : "Nothing matches"
                    }
                    Text {
                        width: parent.width
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.WordWrap
                        color: theme.onSurfaceVariant
                        font.pixelSize: 14
                        visible: !app.refreshing && !library.showHidden
                        text: app.totalCount === 0
                              ? "Connect your stores in Accounts and every game you own settles in here."
                              : library.search ? "No game called \u201c" + library.search + "\u201d" + ((library.tags || []).length || library.installedOnly || library.storeFilter || library.shelf ? " with these filters." : ".")
                              : library.shelf && !(library.tags || []).length && !library.installedOnly ? "This list is empty. Add games to it from a game's page."
                              : "No games match these filters."
                    }
                    Row {
                        anchors.horizontalCenter: parent.horizontalCenter
                        spacing: 8
                        visible: !app.refreshing && !library.showHidden
                        KButton { theme: win.theme; primary: true; visible: app.totalCount === 0; text: qsTr("Connect stores"); onClicked: accounts.open() }
                        KButton { theme: win.theme; visible: app.totalCount === 0; text: qsTr("Add a game"); iconName: "plus"; onClicked: addBox.show() }
                        KButton { theme: win.theme; visible: !!library.search; text: qsTr("Clear search"); iconName: "x"; onClicked: search.text = "" }
                        KButton { theme: win.theme; visible: (library.tags || []).length > 0; text: qsTr("Clear filters"); onClicked: library.tags = [] }
                        KButton { theme: win.theme; visible: library.installedOnly; text: qsTr("Show all games"); onClicked: library.installedOnly = false }
                        KButton { theme: win.theme; visible: !!library.storeFilter || !!library.shelf; text: qsTr("All games"); iconName: "library"
                                  onClicked: { library.storeFilter = ""; library.shelf = "" } }
                    }
                }
            }
        }
    }

    // -------------------------------------------------------------------- game detail
    KDialog {
        id: detail
        objectName: "detail"
        theme: win.theme
        heading: ""
        // The panel takes on the game's own colour (from its cover).
        property string accent: ""
        readonly property var tint: win.tinted(accent)
        Connections {
            target: app
            function onGameColourReady(key, colour) { if (key === win.selectedKey) detail.accent = colour }
            function onDetailsReady(key, d) { if (key === win.selectedKey) detail.info = d }
            function onAchievementsReady(key, d) { if (key === win.selectedKey) detail.ach = d }
            function onDlcsReady(key, rows, note) { if (key === win.selectedKey) detail.dlcCount = rows.length }
        }
        // Description, genres, developer and year (see details.py); filled in when they arrive.
        property var info: ({})
        property var ach: ({})      // Steam achievements: {done, total}
        property int dlcCount: -1   // -1 until known
        onOpened: {
            accent = app.gameColour(win.selectedKey); info = app.gameDetails(win.selectedKey)
            ach = app.achievements(win.selectedKey)
            noteField.text = win.selected.note || ""
            dlcCount = -1
            if (win.selected.hasDlc) app.loadDlcs(win.selectedKey)
            similar = app.similarGames(win.selectedKey)
            detailFlick.contentY = 0
        }
        // A full page over the library (the sidebar stays): Back or Esc returns to where you were.
        x: sidebar.width
        y: 0
        width: win.width - sidebar.width
        height: win.height
        rise: 0
        Overlay.modal: Item { }
        padding: Math.max(28, Math.round((width - 1100) / 2))
        // The game's wide art runs across the top; the cover and title start inside its faded lower part.
        readonly property int bannerH: Math.round(Math.min(height * 0.5, width * 0.4))
        topPadding: bannerH - 150
        bottomPadding: 0
        property var similar: []
        Connections { target: app; function onDetailsGrew() { if (detail.opened) detail.similar = app.similarGames(win.selectedKey) } }
        // Opening grows out of the middle, like the cover it came from.
        enter: Transition {
            enabled: !app.light
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 200; easing.type: Easing.OutCubic }
            NumberAnimation { property: "scale"; from: 0.97; to: 1; duration: 260; easing.type: Easing.OutCubic }
        }
        exit: Transition {
            enabled: !app.light
            NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 140 }
        }
        onAboutToHide: flyer.back()
        onClosed: { win.selectedKey = ""; confirmRemove.armed = false }
        background: Rectangle {
            radius: 0
            color: theme.surfaceContainer
            Item {
                id: detailBanner
                anchors { left: parent.left; right: parent.right; top: parent.top; margins: 1 }
                height: detail.bannerH
                layer.enabled: GraphicsInfo.api !== GraphicsInfo.Software
                layer.effect: MultiEffect { maskEnabled: true; maskSource: detailMask; maskThresholdMin: 0.5; maskSpreadAtMin: 1.0 }
                Rectangle { anchors.fill: parent; color: Qt.darker(win.selected.storeColor || theme.surfaceContainerHigh, 2.6) }
                ArtImage {
                    anchors.fill: parent
                    sources: detail.visible ? (win.selected.heroes || []) : []
                    sourceSize.width: Math.min(3840, Math.max(640, Math.ceil(width * Screen.devicePixelRatio / 40) * 40))
                    opacity: status === Image.Ready ? 1 : 0
                    Behavior on opacity { enabled: !app.light; NumberAnimation { duration: 250 } }
                }
                Rectangle {
                    anchors.fill: parent
                    gradient: Gradient {
                        GradientStop { position: 0.0; color: Qt.alpha(theme.surfaceContainer, 0.0) }
                        GradientStop { position: 0.5; color: Qt.alpha(theme.surfaceContainer, 0.35) }
                        GradientStop { position: 1.0; color: theme.surfaceContainer }
                    }
                }
            }
            Rectangle { id: detailMask; anchors.fill: detailBanner; radius: 0; layer.enabled: true; visible: false }
            Rectangle {  // Back to the library (Esc too)
                anchors { left: parent.left; top: parent.top; margins: 18 }
                width: backRow.implicitWidth + 28; height: 36; radius: 18
                color: closeHover.hovered ? Qt.alpha("black", 0.7) : Qt.alpha("black", 0.45)
                Row { id: backRow; anchors.centerIn: parent; spacing: 6
                      Icon { anchors.verticalCenter: parent.verticalCenter; name: "arrow-left"; size: 16; color: "white" }
                      Text { anchors.verticalCenter: parent.verticalCenter; text: qsTr("Library"); color: "white"; font.pixelSize: 14; font.weight: Font.DemiBold } }
                HoverHandler { id: closeHover; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: detail.close() }
            }
        }
        contentItem: Flickable {
            id: detailFlick
            clip: true
            contentHeight: detailPage.implicitHeight + 40
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: KScrollBar { }
        ColumnLayout {
            id: detailPage
            width: detailFlick.width
            spacing: 28
        RowLayout {
            Layout.fillWidth: true
            spacing: 26
            Item {
                id: detailCoverBox
                Layout.preferredWidth: 220
                Layout.preferredHeight: 320
                Layout.alignment: Qt.AlignTop
                RectangularShadow {
                    anchors.fill: parent
                    visible: !app.light
                    radius: 14; blur: 34; offset.y: 14
                    color: Qt.alpha("black", 0.55)
                }
                RoundedArt {
                anchors.fill: parent
                radius: 14
                Rectangle { anchors.fill: parent; color: theme.surfaceContainerHigh }
                Text {
                    anchors.centerIn: parent
                    width: parent.width - 24
                    text: win.selected.title || ""
                    color: theme.onSurfaceVariant
                    wrapMode: Text.WordWrap
                    horizontalAlignment: Text.AlignHCenter
                    visible: detailArt.status !== Image.Ready
                }
                ArtImage {
                    id: detailArt
                    anchors.fill: parent
                    sources: win.selected.covers || []
                    sourceSize.width: Math.min(400, Math.max(160, Math.ceil(width * Screen.devicePixelRatio / 40) * 40))
                }
                }
                Rectangle {
                    anchors.fill: parent; radius: 14; color: "transparent"
                    border.width: 1; border.color: Qt.alpha("white", 0.12)
                }
            }
            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 10
                Item { Layout.preferredHeight: 34 }
                LogoTitle {
                    Layout.fillWidth: true
                    logos: detail.visible ? (win.selected.logos || []) : []
                    title: win.selected.title || ""
                    color: theme.onSurface
                    pixelSize: 30
                    logoHeight: 84
                    maxWidth: Math.min(width, 440)
                }
                Flow {
                    Layout.fillWidth: true
                    spacing: 8
                    Pill { store: win.selected.store || ""; dot: win.selected.storeColor || ""; label: win.selected.storeName || "" }
                    Pill {
                        label: !win.selected.installed ? qsTr("Not installed") : win.selected.update ? qsTr("↑  Update available") : qsTr("Installed")
                        accent: !!win.selected.update
                    }
                    Pill {
                        readonly property string played: app.playedText(win.selected.playtime, win.selected.lastPlayed)
                        visible: played !== ""
                        label: played
                    }
                }
                // What you came for: Play / Install and friends, right under the title.
                // Job progress.
                ColumnLayout {
                    visible: !!win.selected.job
                    Layout.fillWidth: true
                    spacing: 6
                    Text {
                        color: theme.onSurface
                        font.pixelSize: 13
                        text: win.selected.job === "uninstall" ? qsTr("Removing…")
                              : win.selected.progress < 0 ? "Starting…"
                              : (win.selected.job === "update" ? "Updating  " : win.selected.job === "dlc" ? "Installing DLC  " : "Installing  ")
                                + (win.selected.progress || 0).toFixed(1) + "%"
                                + (win.selected.jobDetail ? "   \u00B7   " + win.selected.jobDetail : "")
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        height: 6; radius: 3
                        color: theme.surfaceContainerHighest
                        Rectangle {
                            height: parent.height; radius: 3
                            color: theme.primary
                            width: parent.width * Math.max(0.02, (win.selected.progress || 0) / 100)
                        }
                    }
                }

                Text {
                    Layout.fillWidth: true
                    visible: win.selected.store === "battlenet" && win.selected.key === "battlenet:battlenet-app"
                    wrapMode: Text.WordWrap
                    color: theme.onSurfaceVariant
                    font.pixelSize: 12
                    text: win.selected.installed
                          ? "Sign in and install Blizzard games inside this app; installed games then show up here as their own tiles."
                          : "Installs Blizzard's launcher under Proton. Its own setup window opens; the first run also downloads Proton."
                }

                Flow {
                    Layout.fillWidth: true
                    spacing: 10
                    KButton {
                        theme: detail.tint
                        primary: true
                        visible: !win.selected.job
                        text: win.selected.installed ? qsTr("Play") : qsTr("Install")
                        iconName: win.selected.installed ? "play" : "download"
                        onClicked: {
                            app.preferCopy(win.selectedKey)
                            win.selected.installed ? app.play(win.selectedKey) : app.install(win.selectedKey)
                        }
                    }
                    KButton {
                        theme: detail.tint
                        visible: !win.selected.job && !!win.selected.update
                        text: qsTr("Update")
                        iconName: "arrow-up"
                        onClicked: app.update(win.selectedKey)
                    }
                    KButton {
                        theme: detail.tint
                        visible: !!win.selected.job
                        text: qsTr("Cancel")
                        iconName: "x"
                        onClicked: app.cancel(win.selectedKey)
                    }
                    KButton {
                        theme: detail.tint
                        visible: !!win.selected.hasDlc && detail.dlcCount !== 0
                        text: detail.dlcCount > 0 ? qsTr("DLC · ") + detail.dlcCount : qsTr("DLC")
                        iconName: "puzzle"
                        onClicked: dlc.show(win.selectedKey, win.selected.title)
                    }
                    KButton {
                        theme: detail.tint
                        text: win.selected.favourite ? qsTr("Favourited") : qsTr("Favourite")
                        iconName: win.selected.favourite ? "star-filled" : "star"
                        onClicked: app.toggleFavourite(win.selectedKey)
                    }
                    // Everything else, one click away.
                    KButton {
                        id: moreBtn
                        theme: detail.tint
                        text: qsTr("More")
                        iconName: "ellipsis"
                        onClicked: moreMenu.opened ? moreMenu.close() : moreMenu.open()
                        Popup {
                            id: moreMenu
                            y: -height - 8
                            width: 240
                            padding: 6
                            onClosed: confirmRemove.armed = false
                            background: Rectangle { radius: 12; color: theme.surfaceContainerHigh; border.width: 1; border.color: theme.outlineVariant }
                            contentItem: Column {
                                spacing: 2
                                MenuRow { icon: "bookmark"; text: (win.selected.collections || []).length ? qsTr("Collections · ") + win.selected.collections.length : qsTr("Add to a collection")
                                          onPicked: { moreMenu.close(); collPick.show(win.selectedKey, win.selected.title) } }
                                MenuRow { icon: "settings-2"; text: qsTr("Options"); onPicked: { moreMenu.close(); gameOpts.show(win.selectedKey) } }
                                MenuRow { icon: "cloud"; text: qsTr("Save backups"); onPicked: { moreMenu.close(); savesBox.show(win.selectedKey, win.selected.title) } }
                                MenuRow { icon: win.selected.hidden ? "eye" : "eye-off"; text: win.selected.hidden ? qsTr("Unhide") : qsTr("Hide")
                                          onPicked: { moreMenu.close(); app.setHidden(win.selectedKey, !win.selected.hidden); detail.close() } }
                                MenuRow {
                                    id: confirmRemove
                                    property bool armed: false
                                    visible: !!win.selected.installed && !win.selected.job && win.selected.store !== "battlenet"
                                    icon: "trash-2"; danger: true
                                    text: armed ? qsTr("Really uninstall?") : qsTr("Uninstall")
                                    onPicked: { if (!armed) { armed = true; return } armed = false; moreMenu.close(); app.uninstall(win.selectedKey) }
                                }
                            }
                        }
                    }
                }
                // Your take on the game: backlog status, stars, a note.
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 6
                    KCombo {
                        id: statusBox
                        theme: detail.tint
                        Layout.preferredWidth: 190
                        model: [{ label: qsTr("No status"), value: "" }].concat(app.statusNames.map(x => ({ label: x.name, value: x.id })))
                        Component.onCompleted: select(win.selected.status || "")
                        Connections { target: win; function onSelectedChanged() { statusBox.select(win.selected.status || "") } }
                        onActivated: app.setStatus(win.selectedKey, currentValue)
                    }
                    Row {
                        spacing: 2
                        Repeater {
                            model: 5
                            Icon {
                                required property int index
                                readonly property bool lit: index < (starHover.hovered ? starHover.at : (win.selected.rating || 0))
                                name: lit ? "star-filled" : "star"
                                size: 20
                                color: lit ? "#ffd166" : theme.outline
                                TapHandler { onTapped: app.setRating(win.selectedKey, (win.selected.rating || 0) === parent.index + 1 ? 0 : parent.index + 1) }
                                HoverHandler { onHoveredChanged: if (hovered) starHover.at = parent.index + 1 }
                            }
                        }
                        HoverHandler { id: starHover; property int at: 0; cursorShape: Qt.PointingHandCursor }
                    }
                }
                KField {
                    id: noteField
                    theme: win.theme
                    Layout.fillWidth: true
                    iconName: "bookmark"
                    placeholderText: qsTr("Your note (where you got to, what to try next)")
                    text: win.selected.note || ""
                    onEditingFinished: app.setNote(win.selectedKey, text)
                }
                Text {
                    Layout.fillWidth: true
                    visible: !!win.selected.installPath
                    text: win.selected.installPath || ""
                    color: theme.outline
                    font.pixelSize: 12
                    elide: Text.ElideMiddle
                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: app.openFolder(win.selected.installPath) }
                }

                // Genres, developer · year, and a short description.
                Flow {
                    Layout.fillWidth: true
                    Layout.topMargin: 4
                    spacing: 6
                    visible: (detail.info.genres || []).length > 0
                    Repeater {
                        model: detail.info.genres || []
                        Rectangle {
                            required property string modelData
                            height: 24; radius: 12
                            width: genreText.implicitWidth + 20
                            color: "transparent"
                            border.width: 1
                            border.color: detail.tint.primary
                            Text { id: genreText; anchors.centerIn: parent; text: modelData; color: detail.tint.primary; font.pixelSize: 11; font.weight: Font.DemiBold }
                        }
                    }
                }
                Text {
                    Layout.fillWidth: true
                    visible: text !== ""
                    text: [detail.info.developer || "", detail.info.year || ""].filter(x => x).join("  ·  ")
                    color: theme.outline
                    font.pixelSize: 12
                }
                // How long to beat (IGDB, when a key is set in Settings > Library)
                RowLayout {
                    Layout.fillWidth: true
                    visible: !!detail.info.ttbLabel
                    spacing: 6
                    Icon { name: "clock"; size: 13; color: theme.outline }
                    Text {
                        Layout.fillWidth: true
                        text: detail.info.ttbLabel || ""
                        color: theme.outline
                        font.pixelSize: 12
                        elide: Text.ElideRight
                    }
                }
                Text {
                    id: detailAbout
                    Layout.fillWidth: true
                    visible: text !== ""
                    text: detail.info.description || ""; textFormat: Text.PlainText
                    color: theme.onSurfaceVariant
                    font.pixelSize: 13
                    lineHeight: 1.25
                    wrapMode: Text.WordWrap
                    maximumLineCount: 5
                    elide: Text.ElideRight
                    opacity: text ? 1 : 0
                    Behavior on opacity { enabled: !app.light; NumberAnimation { duration: 250 } }
                }
                // About how it runs: Linux version, controller, achievements, ProtonDB.
                Flow {
                    Layout.fillWidth: true
                    spacing: 8
                    Pill {
                        visible: win.selected.store === "gog" && (win.selected.platform === "linux" || (!win.selected.installed && !!win.selected.linuxVersion))
                        label: win.selected.platform === "linux" ? qsTr("\u{1F427}  Linux version") : qsTr("\u{1F427}  Has a Linux version")
                    }
                    // Controller support (Steam's store data); not full: Steam Input can map one.
                    Pill {
                        visible: detail.info.controller !== undefined && !!win.selected.steamAppId
                        label: (detail.info.controller === "full" ? qsTr("\u{1F3AE}  Full controller support")
                               : detail.info.controller === "partial" ? "\u{1F3AE}  Partial controller support"
                               : "\u2328  Mouse and keyboard")
                               + (win.selected.store === "steam" && detail.info.controller !== "full" ? "  \u00B7  set up \u2197" : "")
                        accent: false
                        HoverHandler { cursorShape: win.selected.store === "steam" && detail.info.controller !== "full" ? Qt.PointingHandCursor : Qt.ArrowCursor }
                        TapHandler {
                            enabled: win.selected.store === "steam" && detail.info.controller !== "full"
                            onTapped: app.openUrl("steam://controllerconfig/" + win.selected.steamAppId)
                        }
                    }
                    Pill {
                        visible: !!detail.ach.total
                        label: "\u{1F3C6}  " + (detail.ach.done || 0) + " / " + (detail.ach.total || 0) + qsTr(" achievements")
                        accent: !!detail.ach.total && detail.ach.done === detail.ach.total
                    }
                    Pill {
                        visible: !!win.selected.protondb
                        store: "protondb"
                        dot: ProtonDB.color(win.selected.protondb)
                        label: qsTr("ProtonDB: ") + ProtonDB.label(win.selected.protondb)
                               + (win.selected.protondbTrending && win.selected.protondbTrending !== win.selected.protondb
                                  ? " (trending " + ProtonDB.label(win.selected.protondbTrending) + ")" : "")
                        HoverHandler { cursorShape: Qt.PointingHandCursor }
                        TapHandler { onTapped: app.openUrl("https://www.protondb.com/app/" + win.selected.steamAppId) }
                    }
                }
                // Screenshots: click one to see it full size.
                ListView {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 107
                    Layout.topMargin: 4
                    visible: count > 0
                    orientation: ListView.Horizontal
                    spacing: 8
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    model: detail.info.screenshots || []
                    delegate: Item {
                        required property var modelData
                        required property int index
                        width: 176; height: 99
                        scale: shotHover.hovered && !app.light ? 1.04 : 1
                        z: shotHover.hovered ? 1 : 0
                        Behavior on scale { enabled: !app.light; NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
                        RoundedArt {
                        anchors.fill: parent
                        radius: 10
                        Rectangle { anchors.fill: parent; color: theme.surfaceContainerHigh }
                        Image {
                            anchors.fill: parent
                            source: modelData.thumb
                            fillMode: Image.PreserveAspectCrop
                            asynchronous: true
                            sourceSize.width: 300
                            opacity: status === Image.Ready ? 1 : 0
                            Behavior on opacity { enabled: !app.light; NumberAnimation { duration: 200 } }
                        }
                        }
                        Rectangle {
                            anchors.fill: parent; radius: 10; color: "transparent"
                            border.width: shotHover.hovered ? 2 : 1
                            border.color: shotHover.hovered ? detail.tint.primary : Qt.alpha("white", 0.1)
                        }
                        HoverHandler { id: shotHover; cursorShape: Qt.PointingHandCursor }
                        TapHandler { onTapped: viewer.show(detail.info.screenshots, index) }
                    }
                }

                // The same game owned on several stores: choose which copy to use.
                ColumnLayout {
                    visible: (win.selected.copies || []).length > 1
                    Layout.fillWidth: true
                    Layout.topMargin: 6
                    spacing: 8
                    Text {
                        text: qsTr("You own this on ") + (win.selected.copies || []).length + qsTr(" stores. Launcher to use:")
                        color: theme.onSurfaceVariant
                        font.pixelSize: 12
                    }
                    Flow {
                        Layout.fillWidth: true
                        spacing: 8
                        Repeater {
                            model: win.selected.copies || []
                            Chip {
                                required property var modelData
                                label: modelData.storeName + (modelData.installed ? qsTr(" · installed") : "")
                                dot: modelData.storeColor
                                store: modelData.key.split(":")[0]
                                active: modelData.key === win.selectedKey
                                onPicked: {
                                    const k = modelData.key
                                    app.preferCopy(k)
                                    win.selectedKey = k
                                    win.selected = app.game(k)
                                }
                            }
                        }
                    }
                }

                Item { Layout.fillHeight: true }

            }
        }
        // More like this in your library (shared genres, the same developer).
        ColumnLayout {
            visible: detail.similar.length > 0
            Layout.fillWidth: true
            spacing: 10
            Text { text: qsTr("More like this in your library"); color: theme.onSurfaceVariant; font.pixelSize: 14; font.weight: Font.DemiBold }
            ListView {
                Layout.fillWidth: true
                Layout.preferredHeight: 196
                orientation: ListView.Horizontal
                spacing: 12
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                model: detail.similar
                delegate: Item {
                    required property var modelData
                    width: 124; height: 196
                    RoundedArt {
                        width: 124; height: 172; radius: 10
                        opacity: modelData.installed ? 1 : 0.7
                        ArtImage { anchors.fill: parent; sources: modelData.covers || []; sourceSize.width: 248 }
                    }
                    Text { y: 176; width: parent.width; text: modelData.title; color: theme.onSurfaceVariant; font.pixelSize: 11; elide: Text.ElideRight }
                    Rectangle { visible: modelData.unplayed; x: 6; y: 6; height: 20; radius: 10; width: newT.implicitWidth + 14; color: "#cc000000"
                                Text { id: newT; anchors.centerIn: parent; text: qsTr("Not played"); color: "white"; font.pixelSize: 10 } }
                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: { win.select(modelData.key); detail.opened() } }
                }
            }
        }
        Item { Layout.preferredHeight: 20 }
        }
        }
    }

    // -------------------------------------------------------------------- save conflict
    Connections {
        target: app
        function onSaveConflict(key, local, cloud) {
            conflict.key = key
            conflict.title = app.game(key).title || ""
            conflict.local = local
            conflict.cloud = cloud
            conflict.open()
        }
    }
    KDialog {
        id: conflict
        theme: win.theme
        property string key: ""
        property string title: ""
        property string local: ""
        property string cloud: ""
        heading: qsTr("Which saves should ") + title + qsTr(" use?")
        onOpened: useCloud.forceActiveFocus()
        width: Math.min(win.width - 60, 560)
        closePolicy: Popup.CloseOnEscape
        contentItem: ColumnLayout {
            spacing: 14
            Text {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                color: theme.onSurfaceVariant
                font.pixelSize: 13
                text: qsTr("Saves changed both on this PC and in the cloud since the last sync, probably because you played on another computer. The one you don't pick is replaced.")
            }
            KButton {
                id: useCloud
                theme: win.theme; primary: true; Layout.fillWidth: true
                KeyNavigation.down: keepLocal
                Keys.onReturnPressed: clicked()
                text: qsTr("Use the cloud save") + (conflict.cloud ? "  (" + conflict.cloud + ")" : "")
                onClicked: { conflict.close(); app.resolveConflict(conflict.key, "cloud") }
            }
            KButton {
                id: keepLocal
                theme: win.theme; Layout.fillWidth: true
                KeyNavigation.up: useCloud
                KeyNavigation.down: skipSync
                Keys.onReturnPressed: clicked()
                text: qsTr("Keep this PC's save") + (conflict.local ? "  (" + conflict.local + ")" : "")
                onClicked: { conflict.close(); app.resolveConflict(conflict.key, "local") }
            }
            KButton {
                id: skipSync
                theme: win.theme; Layout.fillWidth: true
                KeyNavigation.up: keepLocal
                Keys.onReturnPressed: clicked()
                text: qsTr("Play without syncing this time")
                onClicked: { conflict.close(); app.resolveConflict(conflict.key, "skip") }
            }
        }
    }

    // -------------------------------------------------------------------- storage
    // Every installed game by size, how full each drive is, and Move / Uninstall.
    KDialog {
        id: storage
        objectName: "storageBox"
        theme: win.theme
        heading: qsTr("Storage")
        headingIcon: "folder-open"
        property var d: ({ games: [], drives: [] })
        property bool loading: false
        property bool tidy: false   // "Free up space": big games not played for three months
        property string moveKey: ""
        function show() { loading = true; app.loadStorage(); app.loadPrefixes(); open() }
        Connections { target: app; function onStorageReady(info) { storage.d = info; storage.loading = false } }
        property var prefixes: []
        Connections { target: app; function onPrefixesReady(rows) { storage.prefixes = rows } }
        Connections { target: app; function onGameChanged(key) { if (storage.opened && key && storage.loading === false && !app.game(key).job) app.loadStorage() } }
        width: Math.min(win.width - 60, 820)
        height: Math.min(win.height - 60, 760)
        readonly property var shown: (d.games || []).filter(g => !tidy || (g.bytes > 2 * 1024 * 1024 * 1024
                                       && (!g.last || g.last < Date.now() / 1000 - 90 * 86400)))
        contentItem: ColumnLayout {
            spacing: 14
            // Drives
            Repeater {
                model: storage.d.drives || []
                ColumnLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    spacing: 6
                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: modelData.label + "  (" + modelData.mount + ")"; color: theme.onSurface; font.pixelSize: 14; font.weight: Font.DemiBold; Layout.fillWidth: true; elide: Text.ElideMiddle }
                        Text { text: modelData.freeText + qsTr(" free of ") + modelData.totalText; color: theme.onSurfaceVariant; font.pixelSize: 12 }
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        height: 10; radius: 5
                        color: theme.surfaceContainerHighest
                        Rectangle {  // everything used
                            height: parent.height; radius: 5
                            width: parent.width * modelData.used / Math.max(1, modelData.total)
                            color: Qt.alpha(theme.onSurfaceVariant, 0.45)
                        }
                        Rectangle {  // the games' share
                            height: parent.height; radius: 5
                            width: parent.width * modelData.gameBytes / Math.max(1, modelData.total)
                            color: modelData.free / Math.max(1, modelData.total) < 0.1 ? theme.error : theme.primary
                        }
                    }
                    Text { text: modelData.games + (modelData.games === 1 ? qsTr(" game, ") : qsTr(" games, ")) + modelData.gamesText; color: theme.outline; font.pixelSize: 12 }
                }
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                Text { text: storage.loading ? qsTr("Measuring your games…") : (storage.shown.length + qsTr(" games · ") + (storage.d.total || "")); color: theme.onSurfaceVariant; font.pixelSize: 13; Layout.fillWidth: true }
                KButton {
                    theme: win.theme
                    text: storage.tidy ? qsTr("Show all") : qsTr("Free up space")
                    iconName: storage.tidy ? "library" : "trash-2"
                    onClicked: storage.tidy = !storage.tidy
                }
            }
            // Proton prefixes no installed game uses (and old ones put aside by Reset).
            Rectangle {
                Layout.fillWidth: true
                visible: storage.prefixes.length > 0
                height: pfx.implicitHeight + 20
                radius: 12
                color: theme.surfaceContainerHigh
                ColumnLayout {
                    id: pfx
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 10 }
                    spacing: 6
                    Text {
                        Layout.fillWidth: true; wrapMode: Text.WordWrap
                        text: qsTr("Leftover Proton prefixes (Windows settings of games no longer installed). They can hold saves from games without cloud saves: delete only what you are sure about.")
                        color: theme.onSurfaceVariant; font.pixelSize: 12
                    }
                    Repeater {
                        model: storage.prefixes
                        RowLayout {
                            required property var modelData
                            Layout.fillWidth: true
                            Text { Layout.fillWidth: true; text: modelData.name + (modelData.reset ? qsTr("  (put aside by Reset)") : ""); color: theme.onSurface; font.pixelSize: 13; elide: Text.ElideMiddle }
                            Text { text: modelData.size; color: theme.onSurfaceVariant; font.pixelSize: 12 }
                            KButton { property bool armed: false; theme: win.theme; danger: true; iconName: "trash-2"
                                      text: armed ? qsTr("Sure?") : qsTr("Delete")
                                      onClicked: { if (!armed) { armed = true; return } app.deletePrefix(modelData.path) } }
                        }
                    }
                }
            }
            Text {
                Layout.fillWidth: true
                visible: storage.tidy
                wrapMode: Text.WordWrap
                text: storage.shown.length ? qsTr("Games over 2 GB you haven't played for three months, biggest first.")
                                           : "Nothing to clear: every big game was played lately."
                color: theme.outline; font.pixelSize: 12
            }
            ListView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                spacing: 6
                model: storage.shown
                ScrollBar.vertical: KScrollBar { }
                delegate: Rectangle {
                    required property var modelData
                    readonly property var live: app.game(modelData.key)
                    width: ListView.view.width
                    height: 62; radius: 12
                    color: theme.surfaceContainerHigh
                    RoundedArt {
                        x: 8; anchors.verticalCenter: parent.verticalCenter
                        width: 34; height: 48; radius: 6
                        ArtImage { anchors.fill: parent; sources: modelData.covers || []; sourceSize.width: 68 }
                    }
                    Column {
                        x: 54; anchors.verticalCenter: parent.verticalCenter
                        width: parent.width - 54 - actions.width - 20
                        spacing: 3
                        Text { width: parent.width; text: modelData.title; color: theme.onSurface; font.pixelSize: 14; font.weight: Font.DemiBold; elide: Text.ElideRight }
                        Row {
                            spacing: 6
                            StoreIcon { size: 12; store: modelData.store; color: modelData.storeColor; anchors.verticalCenter: parent.verticalCenter }
                            Text { text: live.job === "move" ? qsTr("Moving ") + Math.max(0, Math.floor(live.progress)) + "%"
                                         : modelData.size + "  ·  played " + modelData.lastText
                                   color: live.job ? theme.primary : theme.onSurfaceVariant; font.pixelSize: 12 }
                        }
                    }
                    Row {
                        id: actions
                        anchors { right: parent.right; rightMargin: 10; verticalCenter: parent.verticalCenter }
                        spacing: 6
                        KButton {
                            theme: win.theme
                            visible: !live.job && modelData.store !== "battlenet"
                            text: qsTr("Move")
                            iconName: "folder-open"
                            onClicked: {
                                if (!modelData.movable) { app.moveGame(modelData.key, ""); return }
                                storage.moveKey = modelData.key
                                moveDest.open()
                            }
                        }
                        KButton {
                            theme: win.theme
                            visible: !!live.job
                            text: qsTr("Cancel")
                            iconName: "x"
                            onClicked: app.cancel(modelData.key)
                        }
                        KButton {
                            id: rmBtn
                            property bool armed: false
                            theme: win.theme
                            danger: true
                            visible: !live.job && modelData.store !== "battlenet"
                            text: armed ? qsTr("Sure?") : qsTr("Uninstall")
                            iconName: "trash-2"
                            onClicked: { if (!armed) { armed = true; return } armed = false; app.uninstall(modelData.key) }
                        }
                    }
                }
            }
        }
    }
    FolderDialog {
        id: backupDest
        title: qsTr("Save the backup in which folder?")
        onAccepted: app.makeBackup(selectedFolder.toString())
    }
    FileDialog {
        id: restoreFile
        title: qsTr("Restore which Cornerplay backup?")
        nameFilters: ["Cornerplay backups (Cornerplay-backup-*.zip)", "Zip files (*.zip)"]
        onAccepted: app.restoreBackup(selectedFile.toString())
    }
    FolderDialog {
        id: syncDest
        title: qsTr("Which folder do your PCs sync?")
        onAccepted: app.setSyncDir(selectedFolder.toString())
    }
    FolderDialog {
        id: romDest
        title: qsTr("Which folder has your ROMs?")
        onAccepted: app.addRomFolder(selectedFolder.toString())
    }
    FolderDialog {
        id: moveDest
        title: qsTr("Move to which folder?")
        onAccepted: app.moveGame(storage.moveKey, selectedFolder.toString())
    }

    // -------------------------------------------------------------------- right-click menu
    // Right-click a cover (library, list, Continue playing), or long-press it on a touchscreen:
    // the things you would otherwise open the game's page for.
    Popup {
        id: gameMenu
        objectName: "gameMenu"
        property string key: ""
        property var g: ({})
        function showFor(k, item, at) {
            key = k
            g = app.game(k)
            if (!g || !g.key) return
            removeRow.armed = false
            const p = item.mapToItem(win.contentItem, at.x, at.y)
            x = Math.max(8, Math.min(p.x, win.width - width - 8))
            y = Math.max(8, Math.min(p.y, win.height - implicitHeight - 8))
            open()
        }
        Connections { target: app; function onGameChanged(k) { if (gameMenu.opened && (k === gameMenu.key || k === "")) gameMenu.g = app.game(gameMenu.key) } }
        parent: win.contentItem
        z: 900
        width: 250
        padding: 6
        modal: false
        focus: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle { radius: 12; color: theme.surfaceContainerHigh; border.width: 1; border.color: theme.outlineVariant }
        contentItem: Column {
            spacing: 2
            Text {
                width: parent.width; leftPadding: 12; rightPadding: 12; topPadding: 6; bottomPadding: 6
                text: gameMenu.g.title || ""; textFormat: Text.PlainText
                color: theme.outline; font.pixelSize: 12; font.weight: Font.DemiBold; elide: Text.ElideRight
            }
            MenuRow {
                visible: !gameMenu.g.job
                icon: gameMenu.g.installed ? "play" : "download"
                text: gameMenu.g.installed ? qsTr("Play") : qsTr("Install")
                onPicked: { const k = gameMenu.key; const inst = gameMenu.g.installed; gameMenu.close(); inst ? win.activate(k) : app.install(k) }
            }
            MenuRow {
                visible: !!gameMenu.g.job
                icon: "x"; text: qsTr("Cancel")
                onPicked: { app.cancel(gameMenu.key); gameMenu.close() }
            }
            MenuRow { icon: "info"; text: qsTr("Details"); onPicked: { const k = gameMenu.key; gameMenu.close(); win.select(k) } }
            MenuRow {
                icon: "star"
                text: gameMenu.g.favourite ? qsTr("Remove from favourites") : qsTr("Add to favourites")
                onPicked: { app.toggleFavourite(gameMenu.key); gameMenu.close() }
            }
            MenuRow { icon: "bookmark"; text: qsTr("Add to a collection")
                      onPicked: { const k = gameMenu.key, t = gameMenu.g.title; gameMenu.close(); collPick.show(k, t) } }
            MenuRow { icon: "settings-2"; text: qsTr("Options"); onPicked: { const k = gameMenu.key; gameMenu.close(); gameOpts.show(k) } }
            MenuRow { icon: "cloud"; text: qsTr("Save backups")
                      onPicked: { const k = gameMenu.key, t = gameMenu.g.title; gameMenu.close(); savesBox.show(k, t) } }
            MenuRow {
                visible: !!gameMenu.g.installed && !!gameMenu.g.installPath
                icon: "folder-open"; text: qsTr("Open folder")
                onPicked: { app.openFolder(gameMenu.g.installPath); gameMenu.close() }
            }
            MenuRow {
                icon: gameMenu.g.hidden ? "eye" : "eye-off"
                text: gameMenu.g.hidden ? qsTr("Unhide") : qsTr("Hide")
                onPicked: { app.setHidden(gameMenu.key, !gameMenu.g.hidden); gameMenu.close() }
            }
            MenuRow {
                id: removeRow
                property bool armed: false
                visible: !!gameMenu.g.installed && !gameMenu.g.job && gameMenu.g.store !== "battlenet" && gameMenu.g.store !== "retro"
                icon: "trash-2"; danger: true
                text: armed ? qsTr("Really uninstall?") : qsTr("Uninstall")
                onPicked: { if (!armed) { armed = true; return } armed = false; app.uninstall(gameMenu.key); gameMenu.close() }
            }
        }
    }

    // -------------------------------------------------------------------- what should I play?
    KDialog {
        id: picker
        objectName: "picker"
        theme: win.theme
        heading: qsTr("What should I play?")
        headingIcon: "gamepad-2"
        property string length: ""
        property bool installedOnly: true
        property var g: ({})
        property var seen: []
        function show() { seen = []; roll(); open() }
        function roll() {
            g = app.pickGame(length, installedOnly, seen.join(","))
            if (g.key) seen = seen.concat([g.key]).slice(-12)
        }
        width: Math.min(win.width - 60, 560)
        contentItem: ColumnLayout {
            spacing: 14
            RowLayout {
                spacing: 6
                Repeater {
                    model: [{ id: "", name: qsTr("Any length") }, { id: "short", name: qsTr("About an hour") }, { id: "long", name: qsTr("A long session") }]
                    Rectangle {
                        required property var modelData
                        readonly property bool on: picker.length === modelData.id
                        height: 32; radius: 16
                        width: lenText.implicitWidth + 28
                        color: on ? theme.primary : "transparent"
                        border.width: on ? 0 : 1; border.color: theme.outlineVariant
                        Text { id: lenText; anchors.centerIn: parent; text: parent.modelData.name; font.pixelSize: 13
                               color: parent.on ? theme.onPrimary : theme.onSurfaceVariant }
                        TapHandler { onTapped: { picker.length = parent.modelData.id; picker.seen = []; picker.roll() } }
                        HoverHandler { cursorShape: Qt.PointingHandCursor }
                    }
                }
                Item { Layout.fillWidth: true }
                Text { text: qsTr("Installed only"); color: theme.onSurfaceVariant; font.pixelSize: 13 }
                Switch {
                    id: pickInst
                    checked: picker.installedOnly
                    onToggled: { picker.installedOnly = checked; picker.seen = []; picker.roll() }
                }
            }
            RowLayout {
                visible: !!picker.g.key
                spacing: 18
                RoundedArt {
                    Layout.preferredWidth: 150; Layout.preferredHeight: 219
                    radius: 14
                    ArtImage { anchors.fill: parent; sources: picker.g.covers || []; sourceSize.width: 300 }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 10
                    Text { Layout.fillWidth: true; text: picker.g.title || ""; color: theme.onSurface; font.pixelSize: 22; font.weight: Font.Bold; wrapMode: Text.WordWrap }
                    Text { Layout.fillWidth: true; text: picker.g.why || ""; color: theme.onSurfaceVariant; font.pixelSize: 14; wrapMode: Text.WordWrap }
                    Text { text: (picker.g.storeName || "") + (picker.g.installed ? "" : qsTr("  ·  not installed")); color: theme.outline; font.pixelSize: 12 }
                    Item { Layout.fillHeight: true }
                    Flow {
                        Layout.fillWidth: true
                        spacing: 8
                        KButton { theme: win.theme; primary: true; text: picker.g.installed ? qsTr("Play") : qsTr("Install"); iconName: picker.g.installed ? "play" : "download"
                                  onClicked: { const k = picker.g.key; picker.close(); picker.g.installed ? win.activate(k) : app.install(k) } }
                        KButton { theme: win.theme; text: qsTr("Another"); iconName: "refresh-cw"; onClicked: picker.roll() }
                        KButton { theme: win.theme; text: qsTr("Details"); onClicked: { const k = picker.g.key; picker.close(); win.select(k) } }
                    }
                }
            }
            Text {
                visible: !picker.g.key
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: picker.installedOnly ? qsTr("Nothing fits: no installed game that isn't finished or dropped. Turn off Installed only to pick from everything.")
                                           : "Nothing fits these choices."
                color: theme.onSurfaceVariant; font.pixelSize: 14
            }
        }
    }

    // -------------------------------------------------------------------- add / import games
    KDialog {
        id: addBox
        objectName: "addBox"
        theme: win.theme
        heading: qsTr("Add games")
        headingIcon: "plus"
        property string exe: ""
        property string importStore: "epic"
        property int heroic: 0
        function show() { exe = ""; addName.text = ""; addArgs.text = ""; heroic = app.heroicCount(); open() }
        width: Math.min(win.width - 60, 620)
        contentItem: ColumnLayout {
            spacing: 16
            // 1. any program
            Text { text: qsTr("A game or app on this PC"); color: theme.onSurface; font.pixelSize: 14; font.weight: Font.DemiBold }
            Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.onSurfaceVariant; font.pixelSize: 12
                   text: qsTr("A Windows program (.exe) runs through Proton in its own prefix; a Linux program runs as it is. It gets covers, playtime, Options and TV mode like any other game.") }
            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                KField { Layout.fillWidth: true; theme: win.theme; readOnly: true; placeholderText: qsTr("No program chosen")
                         text: addBox.exe ? decodeURIComponent(addBox.exe.replace("file://", "")) : "" }
                KButton { theme: win.theme; text: qsTr("Choose…"); iconName: "folder-open"; onClicked: addExe.open() }
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                KField { id: addName; Layout.fillWidth: true; theme: win.theme; placeholderText: qsTr("Name (optional: taken from the file)") }
                KField { id: addArgs; Layout.preferredWidth: 180; theme: win.theme; placeholderText: qsTr("Arguments") }
                KButton { theme: win.theme; primary: true; text: qsTr("Add"); enabled: addBox.exe !== ""
                          onClicked: { app.addGame(addBox.exe, addName.text, addArgs.text); addBox.close() } }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: theme.outlineVariant }
            // 2. already installed
            Text { text: qsTr("Games you already installed"); color: theme.onSurface; font.pixelSize: 14; font.weight: Font.DemiBold }
            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.onSurfaceVariant; font.pixelSize: 12
                       text: qsTr("GOG games: pick the folder they are in (or one game's folder); every GOG game there is found.") }
                KButton { theme: win.theme; text: qsTr("Choose folder…"); iconName: "folder-open"; onClicked: importDir.open() }
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                KCombo { id: impStore; theme: win.theme; Layout.preferredWidth: 130
                         model: [{ label: qsTr("Epic"), value: "epic" }, { label: qsTr("Amazon"), value: "amazon" }]
                         onActivated: addBox.importStore = currentValue }
                KCombo { id: impGame; theme: win.theme; Layout.fillWidth: true
                         model: app.ownedNotInstalled(addBox.importStore).map(g => ({ label: g.title, value: g.id })) }
                KButton { theme: win.theme; text: qsTr("Its folder…"); iconName: "folder-open"; enabled: impGame.count > 0; onClicked: importGameDir.open() }
            }
            // 3. Heroic
            RowLayout {
                visible: addBox.heroic > 0
                Layout.fillWidth: true
                spacing: 8
                Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.onSurfaceVariant; font.pixelSize: 12
                       text: qsTr("Heroic has ") + addBox.heroic + qsTr(" installed game") + (addBox.heroic === 1 ? "" : "s") + qsTr(". Bring them in (nothing is copied or downloaded).") }
                KButton { theme: win.theme; primary: true; text: qsTr("Import from Heroic"); onClicked: { app.importHeroic(); addBox.close() } }
            }
        }
    }
    FileDialog {
        id: addExe
        title: qsTr("Which program?")
        onAccepted: { addBox.exe = selectedFile.toString(); if (!addName.text) addName.text = "" }
    }
    FolderDialog {
        id: importDir
        title: qsTr("Which folder are the GOG games in?")
        onAccepted: { app.importFolder(selectedFolder.toString()); addBox.close() }
    }
    FolderDialog {
        id: importGameDir
        title: qsTr("Where is the game installed?")
        onAccepted: { app.importGame(addBox.importStore, impGame.currentValue, selectedFolder.toString()); addBox.close() }
    }

    // -------------------------------------------------------------------- save backups
    KDialog {
        id: savesBox
        theme: win.theme
        property string key: ""
        property var meta: ({})
        property var rows: []
        property string armed: ""
        heading: qsTr("Save backups")
        headingIcon: "cloud"
        width: Math.min(win.width - 60, 560)
        function show(k, title) { key = k; heading = "Save backups \u00B7 " + title; rows = []; meta = {}; armed = ""; app.loadSaveBackups(k); open() }
        Connections { target: app; function onSavesReady(key, list) { if (key !== savesBox.key) return
                                                                     savesBox.meta = list[0] || {}; savesBox.rows = list.slice(1) } }
        contentItem: ColumnLayout {
            spacing: 12
            Text {
                Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.onSurfaceVariant; font.pixelSize: 13
                text: !savesBox.meta.indexed ? qsTr("Cornerplay is still fetching where games keep their saves; try again in a minute.")
                      : !savesBox.meta.known ? "Cornerplay does not know where this game keeps its saves (it is not in Ludusavi's list)."
                      : savesBox.meta.found ? "Backed up before each start (the last " + app.settingsMap.backup_keep + " are kept). Restoring keeps a copy of what is there now."
                      : "No saves on this PC yet: they are backed up once the game has made some."
            }
            Repeater {
                model: savesBox.rows
                Rectangle {
                    required property var modelData
                    Layout.fillWidth: true
                    height: 52; radius: 12
                    color: theme.surfaceContainerHigh
                    Column {
                        x: 14; anchors.verticalCenter: parent.verticalCenter
                        Text { text: modelData.when; color: theme.onSurface; font.pixelSize: 14; font.weight: Font.DemiBold }
                        Text { text: modelData.reason + "  \u00B7  " + modelData.files + (modelData.files === 1 ? qsTr(" file, ") : qsTr(" files, ")) + modelData.sizeText
                               color: theme.onSurfaceVariant; font.pixelSize: 12 }
                    }
                    KButton {
                        anchors { right: parent.right; rightMargin: 8; verticalCenter: parent.verticalCenter }
                        theme: win.theme
                        text: savesBox.armed === modelData.name ? qsTr("Really put back?") : qsTr("Restore")
                        iconName: "refresh-cw"
                        onClicked: { if (savesBox.armed !== modelData.name) { savesBox.armed = modelData.name; return }
                                     savesBox.armed = ""; app.restoreSaves(savesBox.key, modelData.name) }
                    }
                }
            }
            RowLayout {
                spacing: 8
                KButton { theme: win.theme; primary: true; text: qsTr("Back up now"); iconName: "download"; enabled: !!savesBox.meta.known
                          onClicked: app.backupSavesNow(savesBox.key) }
                KButton { theme: win.theme; text: qsTr("Open folder"); iconName: "folder-open"; onClicked: app.openSaveBackups(savesBox.key) }
            }
        }
    }

    // -------------------------------------------------------------------- health check
    KDialog {
        id: healthBox
        objectName: "healthBox"
        theme: win.theme
        heading: qsTr("Health check")
        headingIcon: "check"
        property var rows: []
        property bool busy: false
        readonly property int bad: rows.filter(r => r.ok === false).length
        function show() { busy = true; app.checkHealth(); open() }
        Connections { target: app; function onHealthReady(rows) { healthBox.rows = rows; healthBox.busy = false } }
        Timer { interval: 5000; running: true; onTriggered: app.checkHealth() }  // once, quietly, after start
        width: Math.min(win.width - 60, 680)
        height: Math.min(win.height - 60, 720)
        contentItem: ColumnLayout {
            spacing: 10
            Text {
                Layout.fillWidth: true
                text: healthBox.busy ? qsTr("Checking…") : healthBox.bad ? healthBox.bad + (healthBox.bad === 1 ? qsTr(" thing needs") : qsTr(" things need")) + qsTr(" fixing")
                                                                    : "Everything games need is in place"
                color: healthBox.bad ? theme.error : theme.onSurfaceVariant; font.pixelSize: 14; font.weight: Font.DemiBold
            }
            ListView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                spacing: 6
                model: healthBox.rows
                ScrollBar.vertical: KScrollBar { }
                delegate: Rectangle {
                    required property var modelData
                    width: ListView.view.width
                    height: Math.max(56, hcol.implicitHeight + 18)
                    radius: 12
                    color: modelData.ok === false ? Qt.alpha(theme.error, 0.12) : theme.surfaceContainerHigh
                    Rectangle {
                        x: 14; anchors.verticalCenter: parent.verticalCenter
                        width: 22; height: 22; radius: 11
                        color: modelData.ok === true ? "#6fd08c" : modelData.ok === false ? theme.error : theme.surfaceContainerHighest
                        Icon { anchors.centerIn: parent; visible: modelData.ok !== null; name: modelData.ok ? "check" : "x"; size: 13; color: "#111" }
                    }
                    Column {
                        id: hcol
                        x: 48; anchors.verticalCenter: parent.verticalCenter
                        width: parent.width - 48 - hfix.width - 24
                        spacing: 3
                        Text { width: parent.width; text: modelData.name; color: theme.onSurface; font.pixelSize: 14; font.weight: Font.DemiBold }
                        Text { width: parent.width; text: modelData.detail; color: theme.onSurfaceVariant; font.pixelSize: 12; wrapMode: Text.WordWrap }
                        Text { width: parent.width; visible: modelData.fix.kind === "command"; text: modelData.fix.command || ""
                               color: theme.primary; font.family: "monospace"; font.pixelSize: 12; wrapMode: Text.WrapAnywhere }
                    }
                    KButton {
                        id: hfix
                        anchors { right: parent.right; rightMargin: 10; verticalCenter: parent.verticalCenter }
                        theme: win.theme
                        visible: !!modelData.fix.kind
                        primary: modelData.ok === false
                        text: modelData.fix.kind === "command" ? qsTr("Copy") : (modelData.fix.label || qsTr("Fix"))
                        onClicked: {
                            const f = modelData.fix
                            if (f.kind === "command") app.copyText(f.command)
                            else if (f.action === "openStorage") { healthBox.close(); storage.show() }
                            else if (f.action === "loginBegin") { healthBox.close(); app.loginBegin(f.arg) }
                            else if (f.action === "fetchBackends") app.fetchBackends()
                            else if (f.action === "downloadGe") app.downloadGe()
                        }
                    }
                }
            }
            KButton { theme: win.theme; text: qsTr("Check again"); iconName: "refresh-cw"; enabled: !healthBox.busy; onClicked: healthBox.show() }
        }
    }

    // -------------------------------------------------------------------- not enough space
    KDialog {
        id: diskBox
        theme: win.theme
        property string key: ""
        property var info: ({})
        heading: info.full ? qsTr("Not enough space for ") + (info.title || "") : (info.title || "") + qsTr(" would nearly fill your drive")
        headingIcon: "folder-open"
        width: Math.min(win.width - 60, 520)
        Connections { target: app; function onDiskWarning(key, info) { diskBox.key = key; diskBox.info = info; diskBox.open() } }
        contentItem: ColumnLayout {
            spacing: 12
            Text {
                Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.onSurfaceVariant; font.pixelSize: 13
                text: (diskBox.info.need ? qsTr("It needs about ") + diskBox.info.need + ". " : "")
                      + diskBox.info.drive + " has " + diskBox.info.free + " free"
                      + (diskBox.info.need ? ", so " + diskBox.info.after + " would be left." : ".")
                      + " Under 10% free slows the PC down and can break updates."
            }
            Text { visible: (diskBox.info.suggest || []).length > 0; text: qsTr("Big games you haven't played for three months:"); color: theme.onSurface; font.pixelSize: 13 }
            Repeater { model: diskBox.info.suggest || []; Text { required property string modelData; text: "\u2022  " + modelData; color: theme.onSurfaceVariant; font.pixelSize: 13 } }
            RowLayout {
                spacing: 8
                KButton { theme: win.theme; primary: true; text: qsTr("Free up space"); iconName: "trash-2"; onClicked: { diskBox.close(); storage.tidy = true; storage.show() } }
                KButton { theme: win.theme; visible: !diskBox.info.full; text: qsTr("Install anyway"); onClicked: { diskBox.close(); app.installAnyway(diskBox.key) } }
            }
        }
    }

    // -------------------------------------------------------------------- a game closed right away
    KDialog {
        id: problemBox
        theme: win.theme
        property string key: ""
        property var p: ({})
        heading: (p.title || qsTr("The game")) + qsTr(" closed right away")
        headingIcon: "x"
        width: Math.min(win.width - 60, 540)
        Connections { target: app; function onLaunchProblem(key, p) { problemBox.key = key; problemBox.p = p; problemBox.open() } }
        contentItem: ColumnLayout {
            spacing: 12
            Text { Layout.fillWidth: true; text: problemBox.p.cause || ""; color: theme.onSurface; font.pixelSize: 16; font.weight: Font.DemiBold; wrapMode: Text.WordWrap }
            Text { Layout.fillWidth: true; text: problemBox.p.detail || ""; color: theme.onSurfaceVariant; font.pixelSize: 13; wrapMode: Text.WordWrap }
            Flow {
                Layout.fillWidth: true
                spacing: 8
                KButton { theme: win.theme; primary: true; visible: problemBox.p.fix === "repair"; text: qsTr("Repair files"); iconName: "refresh-cw"
                          onClicked: { app.fixProblem(problemBox.key, "repair"); problemBox.close() } }
                KButton { theme: win.theme; primary: true; visible: problemBox.p.fix === "vcrun"; text: qsTr("Install Visual C++"); iconName: "download"
                          onClicked: { app.fixProblem(problemBox.key, "vcrun"); problemBox.close() } }
                KButton { theme: win.theme; primary: true; visible: problemBox.p.fix === "dotnet"; text: qsTr("Install .NET"); iconName: "download"
                          onClicked: { app.fixProblem(problemBox.key, "dotnet"); problemBox.close() } }
                KButton { theme: win.theme; primary: problemBox.p.fix === "proton"; visible: problemBox.p.fix === "proton" || problemBox.p.fix === "vcrun"
                          text: qsTr("Try another Proton"); iconName: "settings-2"; onClicked: { problemBox.close(); gameOpts.show(problemBox.key) } }
                KButton { theme: win.theme; primary: true; visible: problemBox.p.fix === "native"; text: qsTr("Use the Windows version"); iconName: "settings-2"
                          onClicked: { problemBox.close(); gameOpts.show(problemBox.key) } }
                KButton { theme: win.theme; primary: true; visible: problemBox.p.fix === "vulkan"; text: qsTr("Open Health check"); iconName: "check"
                          onClicked: { problemBox.close(); healthBox.show() } }
                KButton { theme: win.theme; primary: true; visible: problemBox.p.fix === "storage"; text: qsTr("Free up space"); iconName: "trash-2"
                          onClicked: { problemBox.close(); storage.tidy = true; storage.show() } }
                KButton { theme: win.theme; text: qsTr("Open log"); iconName: "folder-open"; onClicked: app.openLog(problemBox.key) }
                KButton { theme: win.theme; visible: !!win.selectedKey || true; text: qsTr("ProtonDB"); iconName: "external-link"
                          onClicked: { const id = app.game(problemBox.key).steamAppId; app.openUrl(id ? "https://www.protondb.com/app/" + id : "https://www.protondb.com") } }
            }
        }
    }

    // -------------------------------------------------------------------- stats
    KDialog {
        id: statsBox
        objectName: "statsBox"
        theme: win.theme
        heading: qsTr("Your games in numbers")
        headingIcon: "trophy"
        property var d: ({})
        property var yr: ({})
        property int page: 0
        function show() { d = app.stats(); yr = d.year || {}; page = 0; open() }
        width: Math.min(win.width - 60, 760)
        height: Math.min(win.height - 60, 720)
        component Tile: Rectangle {
            property string big: ""
            property string small: ""
            Layout.fillWidth: true
            height: 78; radius: 14
            color: theme.surfaceContainerHigh
            Column {
                anchors.centerIn: parent
                spacing: 2
                Text { anchors.horizontalCenter: parent.horizontalCenter; text: parent.parent.big; color: theme.onSurface; font.pixelSize: 26; font.weight: Font.Bold }
                Text { anchors.horizontalCenter: parent.horizontalCenter; text: parent.parent.small; color: theme.onSurfaceVariant; font.pixelSize: 12 }
            }
        }
        contentItem: Flickable {
            clip: true
            contentHeight: statsCol.implicitHeight
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: KScrollBar { }
            ColumnLayout {
                id: statsCol
                width: parent.width
                spacing: 16
                Row {
                    spacing: 8
                    Chip { label: qsTr("Overview"); icon: "trophy"; active: statsBox.page === 0; onPicked: statsBox.page = 0 }
                    Chip { label: qsTr("Your year"); icon: "sparkles"; active: statsBox.page === 1; onPicked: statsBox.page = 1 }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    visible: statsBox.page === 0
                    spacing: 16
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10
                        Tile { big: (statsBox.d.totalHours || 0) + " h"; small: "played in total" }
                        Tile { big: String(statsBox.d.played || 0); small: "of " + (statsBox.d.games || 0) + " games played" }
                        Tile { big: String(statsBox.d.neverPlayed || 0); small: "never started" }
                        Tile { big: String(statsBox.d.installed || 0); small: "installed" }
                    }
                    // Last 14 days (Cornerplay's own record of Epic, GOG and Amazon sessions).
                    Text { text: qsTr("Last two weeks  ·  ") + (statsBox.d.weekHours || 0) + qsTr(" h this week, ") + (statsBox.d.monthHours || 0) + qsTr(" h this month")
                           color: theme.onSurfaceVariant; font.pixelSize: 13; font.weight: Font.DemiBold }
                    Item {
                        Layout.fillWidth: true
                        height: 110
                        readonly property real peak: Math.max(1, ...(statsBox.d.days || [0]))
                        Row {
                            anchors.fill: parent
                            spacing: 6
                            Repeater {
                                model: statsBox.d.days || []
                                Item {
                                    required property real modelData
                                    width: (parent.width - 13 * 6) / 14
                                    height: parent.height
                                    Rectangle {
                                        anchors.bottom: parent.bottom
                                        width: parent.width
                                        height: Math.max(3, (parent.height - 4) * parent.modelData / parent.parent.parent.peak)
                                        radius: 4
                                        color: parent.modelData > 0 ? theme.primary : theme.surfaceContainerHighest
                                    }
                                }
                            }
                        }
                    }
                    Text {
                        Layout.fillWidth: true
                        visible: (statsBox.d.sessions || 0) === 0
                        wrapMode: Text.WordWrap
                        text: qsTr("Play sessions are logged from now on (games started from Cornerplay on Epic, GOG and Amazon); this chart fills in as you play. Steam only shares totals.")
                        color: theme.outline; font.pixelSize: 12
                    }
                    // The last 12 weeks (sessions Cornerplay saw: its own games, and Steam's while it runs).
                    Text { text: qsTr("Last 12 weeks"); color: theme.onSurfaceVariant; font.pixelSize: 13; font.weight: Font.DemiBold
                           visible: (statsBox.d.sessions || 0) > 0 }
                    Item {
                        Layout.fillWidth: true
                        visible: (statsBox.d.sessions || 0) > 0
                        height: 130
                        readonly property real peak: Math.max(1, ...((statsBox.d.weeks || []).map(w => w.hours)))
                        Row {
                            anchors.fill: parent
                            spacing: 6
                            Repeater {
                                model: statsBox.d.weeks || []
                                Item {
                                    required property var modelData
                                    width: (parent.width - 11 * 6) / 12
                                    height: parent.height
                                    Text { id: wkHours; anchors.horizontalCenter: parent.horizontalCenter; y: wkBar.y - height - 2
                                           visible: modelData.hours > 0; text: modelData.hours; color: theme.onSurfaceVariant; font.pixelSize: 10 }
                                    Rectangle {
                                        id: wkBar
                                        anchors.bottom: wkLabel.top; anchors.bottomMargin: 4
                                        width: parent.width
                                        height: Math.max(3, (parent.height - 36) * modelData.hours / parent.parent.parent.peak)
                                        radius: 4
                                        color: modelData.hours > 0 ? theme.primary : theme.surfaceContainerHighest
                                    }
                                    Text { id: wkLabel; anchors.bottom: parent.bottom; anchors.horizontalCenter: parent.horizontalCenter
                                           text: modelData.label; color: theme.outline; font.pixelSize: 10 }
                                }
                            }
                        }
                    }
                    // Backlog: of the games you meant to play (Playing, Want to play, Finished), how many are done.
                    Text { text: qsTr("Backlog"); color: theme.onSurfaceVariant; font.pixelSize: 13; font.weight: Font.DemiBold }
                    Text {
                        Layout.fillWidth: true
                        visible: !(statsBox.d.backlog || {}).total
                        wrapMode: Text.WordWrap
                        text: qsTr("Mark games as Playing, Want to play or Finished (a game's page, or right-click a cover) to see how far through your backlog you are.")
                        color: theme.outline; font.pixelSize: 12
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        visible: !!(statsBox.d.backlog || {}).total
                        spacing: 6
                        Text { text: (statsBox.d.backlog || {}).done + qsTr(" of ") + (statsBox.d.backlog || {}).total
                                     + qsTr(" finished  ·  ") + (statsBox.d.backlog || {}).percent + "%"
                               color: theme.onSurface; font.pixelSize: 14 }
                        Rectangle {
                            Layout.fillWidth: true
                            height: 10; radius: 5
                            color: theme.surfaceContainerHighest
                            Rectangle { height: parent.height; radius: 5; color: theme.primary
                                        width: parent.width * ((statsBox.d.backlog || {}).percent || 0) / 100 }
                        }
                    }
                    Text { text: qsTr("Most played"); color: theme.onSurfaceVariant; font.pixelSize: 13; font.weight: Font.DemiBold }
                    Repeater {
                        model: statsBox.d.top || []
                        RowLayout {
                            required property var modelData
                            required property int index
                            Layout.fillWidth: true
                            spacing: 12
                            RoundedArt {
                                Layout.preferredWidth: 34; Layout.preferredHeight: 48
                                radius: 6
                                ArtImage { anchors.fill: parent; sources: modelData.covers || []; sourceSize.width: 68 }
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 4
                                RowLayout {
                                    Layout.fillWidth: true
                                    Text { Layout.fillWidth: true; text: modelData.title; color: theme.onSurface; font.pixelSize: 14; elide: Text.ElideRight }
                                    Text { text: modelData.hours + " h"; color: theme.onSurfaceVariant; font.pixelSize: 13 }
                                }
                                Rectangle {
                                    Layout.fillWidth: true
                                    height: 6; radius: 3
                                    color: theme.surfaceContainerHighest
                                    Rectangle {
                                        height: parent.height; radius: 3
                                        width: parent.width * modelData.hours / Math.max(1, (statsBox.d.top[0] || {}).hours || 1)
                                        color: theme.primary
                                    }
                                }
                            }
                        }
                    }
                    Text { text: qsTr("By store"); color: theme.onSurfaceVariant; font.pixelSize: 13; font.weight: Font.DemiBold; visible: (statsBox.d.perStore || []).length > 0 }
                    Flow {
                        Layout.fillWidth: true
                        spacing: 8
                        Repeater {
                            model: statsBox.d.perStore || []
                            Pill { required property var modelData; label: modelData.name + "  ·  " + modelData.hours + " h" }
                        }
                        Repeater {
                            model: statsBox.d.statuses || []
                            Pill { required property var modelData; label: modelData.name + "  ·  " + modelData.count; accent: true }
                        }
                    }
                }
                // ---- Your year
                ColumnLayout {
                    Layout.fillWidth: true
                    visible: statsBox.page === 1
                    spacing: 16
                    readonly property var yr: statsBox.yr
                    Flow {
                        Layout.fillWidth: true
                        spacing: 8
                        visible: (statsBox.d.years || []).length > 1
                        Repeater {
                            model: statsBox.d.years || []
                            Chip { required property int modelData; label: String(modelData); active: statsBox.yr.year === modelData
                                   onPicked: statsBox.yr = app.yearStats(modelData) }
                        }
                    }
                    Text { text: qsTr("Your ") + (parent.yr.year || "") + qsTr(" in Cornerplay"); color: theme.onSurface
                           font.pixelSize: 22; font.weight: Font.Bold }
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10
                        Tile { big: (parent.parent.yr.hours || 0) + " h"; small: qsTr("played") }
                        Tile { big: String(parent.parent.yr.games || 0); small: qsTr("games played") }
                        Tile { big: String(parent.parent.yr.newCount || 0); small: qsTr("started for the first time") }
                        Tile { big: String(parent.parent.yr.finishedCount || 0); small: qsTr("finished") }
                    }
                    Text {
                        Layout.fillWidth: true
                        visible: !(parent.yr.hours > 0)
                        wrapMode: Text.WordWrap
                        text: qsTr("Hours fill in from the play sessions Cornerplay sees: the games it starts, and Steam games while Cornerplay is running (start it with the PC in Settings > Advanced to catch them all).")
                        color: theme.outline; font.pixelSize: 12
                    }
                    Text {
                        Layout.fillWidth: true
                        visible: !!parent.yr.busiestMonth
                        wrapMode: Text.WordWrap
                        text: qsTr("Busiest month: ") + parent.yr.busiestMonth + " (" + parent.yr.busiestHours + " h)"
                              + ((parent.yr.longest || {}).title ? qsTr("  ·  Longest session: ") + parent.yr.longest.title + ", "
                                 + parent.yr.longest.hours + " h on " + parent.yr.longest.date : "")
                        color: theme.onSurface; font.pixelSize: 14
                    }
                    // Hours per month
                    Item {
                        Layout.fillWidth: true
                        visible: parent.yr.hours > 0
                        height: 120
                        readonly property real peak: Math.max(1, ...((statsBox.yr.months || [0])))
                        Row {
                            anchors.fill: parent
                            spacing: 6
                            Repeater {
                                model: statsBox.yr.months || []
                                Item {
                                    required property real modelData
                                    required property int index
                                    width: (parent.width - 11 * 6) / 12
                                    height: parent.height
                                    Rectangle {
                                        anchors.bottom: mLabel.top; anchors.bottomMargin: 4
                                        width: parent.width
                                        height: Math.max(3, (parent.height - 22) * modelData / parent.parent.parent.peak)
                                        radius: 4
                                        color: modelData > 0 ? theme.primary : theme.surfaceContainerHighest
                                    }
                                    Text { id: mLabel; anchors.bottom: parent.bottom; anchors.horizontalCenter: parent.horizontalCenter
                                           text: "JFMAMJJASOND"[index]; color: theme.outline; font.pixelSize: 10 }
                                }
                            }
                        }
                    }
                    Text { text: qsTr("Most played"); color: theme.onSurfaceVariant; font.pixelSize: 13; font.weight: Font.DemiBold
                           visible: (parent.yr.top || []).length > 0 }
                    Repeater {
                        model: statsBox.yr.top || []
                        RowLayout {
                            required property var modelData
                            required property int index
                            Layout.fillWidth: true
                            spacing: 12
                            Text { text: (index + 1) + "."; color: theme.outline; font.pixelSize: 14; Layout.preferredWidth: 22 }
                            Text { Layout.fillWidth: true; text: modelData.title; color: theme.onSurface; font.pixelSize: 14; elide: Text.ElideRight }
                            Text { text: modelData.hours + " h"; color: theme.onSurfaceVariant; font.pixelSize: 13 }
                        }
                    }
                    Text { text: qsTr("Finished"); color: theme.onSurfaceVariant; font.pixelSize: 13; font.weight: Font.DemiBold
                           visible: (parent.yr.finished || []).length > 0 }
                    Flow {
                        Layout.fillWidth: true
                        spacing: 8
                        Repeater { model: statsBox.yr.finished || []; Pill { required property string modelData; label: modelData; accent: true } }
                    }
                    Text { text: qsTr("Started for the first time"); color: theme.onSurfaceVariant; font.pixelSize: 13; font.weight: Font.DemiBold
                           visible: (parent.yr.newGames || []).length > 0 }
                    Flow {
                        Layout.fillWidth: true
                        spacing: 8
                        Repeater { model: statsBox.yr.newGames || []; Pill { required property string modelData; label: modelData } }
                    }
                }
            }
        }
    }

    // -------------------------------------------------------------------- downloads
    // What is downloading, what waits its turn, and what is paused: reorder, pause, resume, cancel,
    // and a speed limit (throttle.py) so a big download leaves room for everything else.
    KDialog {
        id: downloadsBox
        objectName: "downloadsBox"
        theme: win.theme
        heading: qsTr("Downloads")
        headingIcon: "download"
        width: Math.min(win.width - 60, 640)
        height: Math.min(win.height - 60, 560)
        function nice(secs) { return secs < 60 ? qsTr("under a minute left") : secs < 3600 ? Math.round(secs / 60) + qsTr(" min left")
                                     : Math.floor(secs / 3600) + " h " + Math.round((secs % 3600) / 60) + qsTr(" min left") }
        contentItem: ColumnLayout {
            spacing: 12
            Text {
                Layout.fillWidth: true
                visible: app.downloads.length === 0
                wrapMode: Text.WordWrap
                text: qsTr("Nothing is downloading.")
                color: theme.onSurfaceVariant; font.pixelSize: 13
            }
            ListView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                spacing: 8
                model: app.downloads
                ScrollBar.vertical: KScrollBar { }
                delegate: Rectangle {
                    required property var modelData
                    required property int index
                    width: ListView.view.width
                    height: 76; radius: 12
                    color: theme.surfaceContainerHigh
                    border.width: modelData.state === "running" ? 1 : 0; border.color: theme.primary
                    RowLayout {
                        anchors { fill: parent; leftMargin: 10; rightMargin: 8 }
                        spacing: 12
                        RoundedArt {
                            Layout.preferredWidth: 40; Layout.preferredHeight: 56
                            radius: 6
                            ArtImage { anchors.fill: parent; sources: modelData.covers || []; sourceSize.width: 80 }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 5
                            Text { Layout.fillWidth: true; text: modelData.title; color: theme.onSurface; font.pixelSize: 14
                                   font.weight: Font.DemiBold; elide: Text.ElideRight }
                            Text {
                                Layout.fillWidth: true
                                elide: Text.ElideRight
                                color: theme.onSurfaceVariant; font.pixelSize: 12
                                text: {
                                    const d = modelData
                                    const what = ({ install: qsTr("Installing"), update: qsTr("Updating"), dlc: qsTr("Installing DLC"),
                                                    verify: qsTr("Checking files"), move: qsTr("Moving"), fix: qsTr("Fixing") })[d.kind] || d.kind
                                    if (d.state === "queued") return qsTr("Waiting its turn  ·  ") + what
                                    if (d.state === "paused") return qsTr("Paused") + (d.progress >= 0 ? "  ·  " + Math.floor(d.progress) + "%" : "")
                                    const parts = [what + (d.progress >= 0 ? " " + Math.floor(d.progress) + "%" : "…")]
                                    if (d.speed > 0) parts.push(d.speed >= 1e6 ? (d.speed / 1e6).toFixed(1) + " MB/s" : Math.round(d.speed / 1e3) + " kB/s")
                                    if (d.eta >= 0) parts.push(downloadsBox.nice(d.eta))
                                    return parts.join("  ·  ")
                                }
                            }
                            Rectangle {
                                Layout.fillWidth: true
                                height: 5; radius: 3
                                color: theme.surfaceContainerHighest
                                Rectangle { height: parent.height; radius: 3; width: parent.width * Math.max(0, modelData.progress) / 100
                                            color: modelData.state === "running" ? theme.primary : theme.outline }
                            }
                        }
                        KButton { theme: win.theme; visible: modelData.state === "queued"; iconName: "chevron-up"; text: ""
                                  enabled: index > 0 && app.downloads[index - 1].state === "queued"
                                  ToolTip.visible: hovered; ToolTip.text: qsTr("Earlier"); onClicked: app.moveDownload(modelData.key, -1) }
                        KButton { theme: win.theme; visible: modelData.state === "queued"; iconName: "chevron-down"; text: ""
                                  enabled: index + 1 < app.downloads.length && app.downloads[index + 1].state === "queued"
                                  ToolTip.visible: hovered; ToolTip.text: qsTr("Later"); onClicked: app.moveDownload(modelData.key, 1) }
                        KButton { theme: win.theme; visible: modelData.pausable && modelData.state !== "paused"; text: qsTr("Pause")
                                  onClicked: app.pauseDownload(modelData.key) }
                        KButton { theme: win.theme; primary: true; visible: modelData.state === "paused"; text: qsTr("Resume"); iconName: "download"
                                  onClicked: app.resumeDownload(modelData.key) }
                        KButton { theme: win.theme; iconName: "x"; text: ""; ToolTip.visible: hovered; ToolTip.text: qsTr("Cancel")
                                  onClicked: app.cancel(modelData.key) }
                    }
                }
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: 10
                Text { text: qsTr("Speed limit"); color: theme.onSurface; font.pixelSize: 13 }
                KField {
                    theme: win.theme
                    Layout.preferredWidth: 90
                    placeholderText: qsTr("none")
                    text: app.settingsMap.download_limit > 0 ? String(app.settingsMap.download_limit) : ""
                    validator: DoubleValidator { bottom: 0; top: 10000; decimals: 1; notation: DoubleValidator.StandardNotation }
                    onEditingFinished: app.setSetting("download_limit", parseFloat(text.replace(",", ".")) || 0)
                }
                Text { Layout.fillWidth: true; text: qsTr("MB/s for Epic, GOG and Amazon (empty: as fast as it goes)")
                       color: theme.onSurfaceVariant; font.pixelSize: 12; elide: Text.ElideRight }
            }
        }
    }

    // -------------------------------------------------------------------- collections
    // Which collections a game is in: one row per collection, tap to add or remove.
    KDialog {
        id: collPick
        theme: win.theme
        property string key: ""
        property var inList: []
        heading: qsTr("Collections")
        headingIcon: "bookmark"
        width: Math.min(win.width - 60, 420)
        function show(k, title) { key = k; heading = title; inList = app.game(k).collections || []; open() }
        Connections { target: app; function onCollectionsChanged() { if (collPick.opened) collPick.inList = app.game(collPick.key).collections || [] } }
        contentItem: ColumnLayout {
            spacing: 8
            Text {
                visible: app.collections.length === 0
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: qsTr("No collections yet. Make one for the games you play together, a backlog, anything.")
                color: theme.onSurfaceVariant; font.pixelSize: 13
            }
            Repeater {
                model: app.collections
                Rectangle {
                    required property string modelData
                    readonly property bool on: collPick.inList.indexOf(modelData) !== -1
                    Layout.fillWidth: true
                    height: 44; radius: 10
                    color: collRowHover.hovered ? theme.surfaceContainerHigh : "transparent"
                    Rectangle {
                        x: 12; anchors.verticalCenter: parent.verticalCenter
                        width: 20; height: 20; radius: 6
                        color: parent.on ? theme.primary : "transparent"
                        border.width: parent.on ? 0 : 2; border.color: theme.outline
                        Icon { anchors.centerIn: parent; visible: parent.parent.on; name: "check"; size: 14; color: theme.onPrimary }
                    }
                    Text { x: 44; anchors.verticalCenter: parent.verticalCenter; text: parent.modelData; color: theme.onSurface; font.pixelSize: 14 }
                    HoverHandler { id: collRowHover; cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: app.setInCollection(collPick.key, parent.modelData, !parent.on) }
                }
            }
            KButton {
                theme: win.theme
                Layout.fillWidth: true
                text: qsTr("New collection")
                iconName: "plus"
                onClicked: { const k = collPick.key; collPick.close(); newColl.ask(k) }
            }
        }
    }
    KDialog {
        id: newColl
        theme: win.theme
        property string addKey: ""   // a game to put in the new collection straight away
        heading: qsTr("New collection")
        headingIcon: "bookmark"
        width: Math.min(win.width - 60, 420)
        function ask(k) { addKey = k; collName.text = ""; open() }
        onOpened: collName.forceActiveFocus()
        function create() {
            const made = app.createCollection(collName.text)
            if (!made) { collName.text = ""; return }
            if (addKey) app.setInCollection(addKey, made, true)
            close()
        }
        contentItem: ColumnLayout {
            spacing: 14
            KField {
                id: collName
                theme: win.theme
                Layout.fillWidth: true
                placeholderText: qsTr("Name, e.g. Co-op nights")
                Keys.onReturnPressed: newColl.create()
                Keys.onEnterPressed: newColl.create()
            }
            KButton { theme: win.theme; primary: true; Layout.fillWidth: true; text: qsTr("Create"); enabled: collName.text.trim() !== ""; onClicked: newColl.create() }
        }
    }
    KDialog {
        id: removeColl
        theme: win.theme
        property string name: ""
        heading: qsTr("Delete \u201c") + name + "\u201d?"
        width: Math.min(win.width - 60, 420)
        contentItem: ColumnLayout {
            spacing: 14
            Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.onSurfaceVariant; font.pixelSize: 13
                   text: qsTr("The collection goes away; the games stay in your library.") }
            KButton { theme: win.theme; danger: true; Layout.fillWidth: true; text: qsTr("Delete collection"); iconName: "trash-2"
                      onClicked: { app.deleteCollection(removeColl.name); removeColl.close() } }
        }
    }

    // -------------------------------------------------------------------- DLC
    KDialog {
        id: dlc
        objectName: "dlc"
        theme: win.theme
        property string key: ""
        property var rows: []
        property string note: ""
        property bool loading: false
        property string error: ""
        property bool busy: false   // a DLC install for this game is running
        heading: qsTr("DLC")
        headingIcon: "puzzle"
        width: Math.min(win.width - 60, 680)
        function show(k, title) {
            key = k; rows = []; note = ""; error = ""; loading = true
            busy = app.game(k).job === "dlc"
            heading = "DLC · " + title
            open()
            app.loadDlcs(k)
        }
        Connections {
            target: app
            function onDlcsReady(key, rows, note) {
                if (key !== dlc.key) return
                dlc.rows = rows; dlc.loading = false
                // a store message without rows is an error; with rows it is a note
                const isNote = note.indexOf("Steam installs") === 0 || note.indexOf("Epic lists") === 0
                if (rows.length) { dlc.note = note; dlc.error = "" } else { dlc.error = isNote ? "" : note; dlc.note = "" }
            }
            function onGameChanged(key) {
                // the DLC install finished: show the new state
                if (key === dlc.key && dlc.busy && app.game(key).job !== "dlc") { dlc.busy = false; app.loadDlcs(key, true) }
            }
        }
        contentItem: ColumnLayout {
            spacing: 12
            readonly property var counts: {
                const c = { installed: 0, owned: 0, missing: 0, available: 0 }
                for (const r of dlc.rows) c[r.status] = (c[r.status] || 0) + 1
                return c
            }
            // Summary: how many, and what you have.
            Text {
                Layout.fillWidth: true
                visible: dlc.rows.length > 0
                color: theme.onSurfaceVariant
                font.pixelSize: 13
                text: {
                    const c = parent.counts, parts = [dlc.rows.length + " DLC"]
                    if (c.installed) parts.push(c.installed + " installed")
                    if (c.owned) parts.push(c.owned + " owned, not installed")
                    if (c.available) parts.push(c.available + " to buy")
                    return parts.join("  ·  ")
                }
            }
            Text {
                Layout.fillWidth: true
                visible: dlc.loading || dlc.rows.length === 0
                color: theme.onSurfaceVariant
                font.pixelSize: 13
                wrapMode: Text.WordWrap
                text: dlc.loading ? qsTr("Looking up DLC…") : (dlc.error || qsTr("No DLC found for this game."))
            }
            // Install all owned DLC at once (GOG installs them together anyway).
            KButton {
                theme: win.theme
                primary: true
                iconName: "download"
                visible: !dlc.busy && dlc.rows.filter(r => r.canInstall).length > 1
                text: qsTr("Install all owned DLC")
                onClicked: { const r = dlc.rows.find(r => r.canInstall); if (r) { dlc.busy = true; app.installDlc(dlc.key, r.id) } }
            }
            Text {
                visible: dlc.busy
                color: theme.primary
                font.pixelSize: 13
                font.weight: Font.DemiBold
                text: qsTr("Installing DLC… ") + (win.selected.job === "dlc" && win.selected.progress >= 0 ? Math.floor(win.selected.progress) + "%" : "")
            }
            ListView {
                id: dlcList
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(contentHeight, Math.max(240, win.height - 320))
                visible: dlc.rows.length > 0
                clip: true
                spacing: 8
                model: dlc.rows
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: KScrollBar { }
                delegate: Rectangle {
                    id: dlcRow
                    required property var modelData
                    readonly property var info: ({
                        installed: { label: qsTr("Installed"), icon: "check" },
                        owned: { label: qsTr("Owned"), icon: "check" },
                        missing: { label: qsTr("Not installed"), icon: "" },
                        available: { label: qsTr("Not owned"), icon: "" } })[modelData.status] || { label: modelData.status, icon: "" }
                    width: dlcList.width - 10
                    height: 76
                    radius: 12
                    color: theme.surfaceContainerHigh
                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 8
                        anchors.rightMargin: 12
                        spacing: 14
                        // The DLC's own art (wide), or a placeholder tile.
                        Rectangle {
                            Layout.preferredWidth: 128
                            Layout.preferredHeight: 60
                            radius: 8
                            color: theme.surfaceContainerHighest
                            clip: true
                            Icon { anchors.centerIn: parent; name: "puzzle"; size: 22; color: theme.outline; visible: dlcArt.status !== Image.Ready }
                            Image {
                                id: dlcArt
                                anchors.fill: parent
                                source: dlcRow.modelData.image || ""
                                fillMode: Image.PreserveAspectCrop
                                asynchronous: true
                                sourceSize.width: 256
                                opacity: status === Image.Ready ? (dlcRow.modelData.status === "available" ? 0.7 : 1) : 0
                                Behavior on opacity { enabled: !app.light; NumberAnimation { duration: 200 } }
                            }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 5
                            Text {
                                Layout.fillWidth: true
                                text: dlcRow.modelData.title
                                color: theme.onSurface
                                font.pixelSize: 14
                                font.weight: Font.DemiBold
                                elide: Text.ElideRight
                            }
                            Row {
                                spacing: 8
                                Rectangle {
                                    readonly property bool have: dlcRow.modelData.status === "installed" || dlcRow.modelData.status === "owned"
                                    height: 22; radius: 11
                                    width: stRow.implicitWidth + 18
                                    color: have ? theme.primaryContainer : "transparent"
                                    border.width: have ? 0 : 1
                                    border.color: theme.outlineVariant
                                    Row {
                                        id: stRow
                                        anchors.centerIn: parent
                                        spacing: 5
                                        Icon { visible: dlcRow.info.icon !== ""; name: dlcRow.info.icon; size: 12; color: theme.onPrimaryContainer; anchors.verticalCenter: parent.verticalCenter }
                                        Text {
                                            anchors.verticalCenter: parent.verticalCenter
                                            text: dlcRow.info.label
                                            font.pixelSize: 11
                                            font.weight: Font.DemiBold
                                            color: parent.parent.have ? theme.onPrimaryContainer : theme.onSurfaceVariant
                                        }
                                    }
                                }
                                Text {
                                    visible: !!dlcRow.modelData.price
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: dlcRow.modelData.price || ""
                                    color: theme.onSurfaceVariant
                                    font.pixelSize: 12
                                }
                            }
                        }
                        KButton {
                            theme: win.theme
                            implicitHeight: 34
                            primary: true
                            iconName: "download"
                            visible: !!dlcRow.modelData.canInstall && !dlc.busy
                            text: qsTr("Install")
                            onClicked: { dlc.busy = true; app.installDlc(dlc.key, dlcRow.modelData.id) }
                        }
                        KButton {
                            theme: win.theme
                            implicitHeight: 34
                            iconName: "external-link"
                            visible: !dlcRow.modelData.canInstall && !!dlcRow.modelData.url
                            text: dlcRow.modelData.url.indexOf("steam://") === 0 ? qsTr("Open in Steam") : qsTr("Store page")
                            onClicked: app.openUrl(dlcRow.modelData.url)
                        }
                    }
                }
            }
            Text {
                Layout.fillWidth: true
                visible: dlc.note !== "" && dlc.rows.length > 0
                wrapMode: Text.WordWrap
                color: theme.outline
                font.pixelSize: 12
                text: dlc.note
            }
        }
    }

    // -------------------------------------------------------------------- accounts
    KDialog {
        id: accounts
        objectName: "accounts"
        theme: win.theme
        heading: qsTr("Accounts")
        headingIcon: "user-round"
        width: Math.min(win.width - 60, 620)
        contentItem: ColumnLayout {
            spacing: 10
            Repeater {
                model: app.storesInfo.filter(s => s.inAccounts)
                Rectangle {
                    required property var modelData
                    Layout.fillWidth: true
                    height: Math.max(78, accountRow.implicitHeight + 34)
                    radius: 14
                    color: theme.surfaceContainerHigh
                    border.width: 1
                    border.color: modelData.loggedIn ? Qt.alpha(modelData.color, 0.45) : theme.outlineVariant
                    RowLayout {
                        id: accountRow
                        anchors.fill: parent
                        anchors.leftMargin: 14; anchors.rightMargin: 12
                        spacing: 14
                        // The store's logo on a soft tile of its colour.
                        Rectangle {
                            Layout.preferredWidth: 48; Layout.preferredHeight: 48
                            radius: 12
                            color: Qt.alpha(modelData.color, 0.16)
                            StoreIcon { anchors.centerIn: parent; size: 28; store: modelData.id; color: modelData.color }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 4
                            Text { text: modelData.name; color: theme.onSurface; font.pixelSize: 15; font.weight: Font.DemiBold }
                            Row {
                                spacing: 7
                                Layout.fillWidth: true
                                Rectangle {
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: 8; height: 8; radius: 4
                                    color: modelData.problem ? theme.error : modelData.loggedIn ? "#6fd08c" : theme.outline
                                }
                                Text {
                                    width: parent.parent.width - 15
                                    elide: Text.ElideRight
                                    font.pixelSize: 12
                                    color: modelData.problem ? theme.error : theme.onSurfaceVariant
                                text: modelData.problem ? modelData.problem
                                      : modelData.loggedIn ? ("Connected" + (modelData.account ? " · " + modelData.account : ""))
                                      : modelData.id === "battlenet" ? "Install the Battle.net app from the library, or link your Blizzard account to list your games"
                                      : "Not connected"
                                }
                            }
                            // Steam without a Web API key: say what is listed, and where to get the rest.
                            Text {
                                Layout.fillWidth: true
                                visible: modelData.id === "steam" && modelData.loggedIn && !app.settingsMap.steam_api_key
                                wrapMode: Text.WordWrap
                                font.pixelSize: 11
                                color: theme.outline
                                linkColor: theme.primary
                                text: qsTr("Showing installed games and games you have played. For every game you own, ")
                                      + "<a href=\"key\">add a Steam Web API key</a>."
                                onLinkActivated: { accounts.close(); prefs.tab = 3; prefs.open() }
                                HoverHandler { cursorShape: parent.hoveredLink ? Qt.PointingHandCursor : Qt.ArrowCursor }
                            }
                        }
                        KButton {
                            theme: win.theme
                            visible: modelData.id === "battlenet" && typeof webLogin !== "undefined" && webLogin
                            text: app.blizzardLinked ? qsTr("Unlink account") : qsTr("Link account")
                            iconName: app.blizzardLinked ? "log-out" : "log-in"
                            onClicked: app.blizzardLinked ? app.blizzardUnlink() : app.blizzardLink()
                        }
                        KButton {
                            theme: win.theme
                            visible: modelData.loginKind === "paste" && modelData.loggedIn
                            text: qsTr("Sign out")
                            iconName: "log-out"
                            onClicked: app.logout(modelData.id)
                        }
                        KButton {
                            theme: win.theme
                            primary: !modelData.loggedIn
                            visible: !(modelData.loginKind === "paste" && modelData.loggedIn)
                            enabled: modelData.id === "gog" || !modelData.problem
                            text: modelData.loginKind === "external" ? qsTr("Open") : qsTr("Sign in")
                            iconName: modelData.loginKind === "external" ? "external-link" : "log-in"
                            onClicked: app.loginBegin(modelData.id)
                        }
                    }
                }
            }
            Text {
                Layout.fillWidth: true
                Layout.topMargin: 4
                wrapMode: Text.WordWrap
                color: theme.outline
                font.pixelSize: 12
                text: qsTr("Sign-ins happen in your browser or in the store's own client. Cornerplay never sees your passwords; it only keeps the session tokens the stores hand back.")
            }
        }
    }

    // -------------------------------------------------------------------- paste-code sign-in
    KDialog {
        id: login
        theme: win.theme
        property string store: ""
        property string url: ""
        property string prompt: ""
        property string error: ""
        property bool busy: false
        heading: qsTr("Sign in to ") + (win.storeInfo(store).name || "")
        width: Math.min(win.width - 60, 560)
        closePolicy: Popup.CloseOnEscape
        function submit() {
            if (!code.text.trim() || busy) return
            busy = true; error = ""
            app.loginFinish(store, code.text)
        }
        contentItem: ColumnLayout {
            spacing: 14
            Text {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                color: theme.onSurfaceVariant
                font.pixelSize: 13
                lineHeight: 1.25
                text: login.prompt
            }
            RowLayout {
                spacing: 10
                KButton { theme: win.theme; iconName: "external-link"; text: qsTr("Open login page again"); onClicked: app.openUrl(login.url) }
                KButton { theme: win.theme; text: qsTr("Copy link"); onClicked: { app.copy(login.url); toasts.append({ message: qsTr("Link copied") }) } }
            }
            KField {
                id: code
                theme: win.theme
                Layout.fillWidth: true
                placeholderText: qsTr("Paste here")
                onAccepted: login.submit()
            }
            Text {
                Layout.fillWidth: true
                visible: login.error !== ""
                wrapMode: Text.WordWrap
                color: theme.error
                font.pixelSize: 12
                text: login.error
            }
            KButton {
                theme: win.theme
                primary: true
                Layout.alignment: Qt.AlignRight
                enabled: code.text.trim() !== "" && !login.busy
                text: login.busy ? qsTr("Checking…") : qsTr("Finish sign-in")
                onClicked: login.submit()
            }
        }
    }

    // -------------------------------------------------------------------- settings
    // One setting, as a card: name, the control, and an optional hint underneath.
    component Row2: Rectangle {
        id: r2
        readonly property var theme: app.theme
        property string label
        property string hint: ""
        default property alias body: slot.data
        readonly property bool hit: prefs.query !== "" && (label + " " + hint).toLowerCase().indexOf(prefs.query) !== -1
        Layout.fillWidth: true
        implicitHeight: r2col.implicitHeight + 28
        radius: 12
        color: theme.surfaceContainerHigh
        border.width: hit ? 2 : 0; border.color: theme.primary
        ColumnLayout {
            id: r2col
            anchors { left: parent.left; right: parent.right; top: parent.top; margins: 14 }
            spacing: 8
            Text { visible: r2.label !== ""; text: r2.label; color: r2.theme.onSurface; font.pixelSize: 13; font.weight: Font.DemiBold }
            ColumnLayout { id: slot; Layout.fillWidth: true }
            Text {
                visible: r2.hint !== ""
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: r2.hint
                color: r2.theme.outline
                font.pixelSize: 12
                lineHeight: 1.15
                linkColor: r2.theme.primary
                onLinkActivated: link => app.openUrl(link)
            }
        }
    }
    // An on/off setting, as a card row.
    component Toggle: Rectangle {
        id: tg
        readonly property var theme: app.theme
        property string label
        property string settingKey
        property var act: null  // set: called with the new state instead of saving settingKey
        readonly property bool hit: prefs.query !== "" && label.toLowerCase().indexOf(prefs.query) !== -1
        Layout.fillWidth: true
        implicitHeight: 48
        radius: 12
        color: theme.surfaceContainerHigh
        border.width: hit ? 2 : 0; border.color: theme.primary
        Text {
            anchors { left: parent.left; leftMargin: 14; right: sw.left; rightMargin: 10; verticalCenter: parent.verticalCenter }
            text: tg.label; color: tg.theme.onSurface; font.pixelSize: 13; elide: Text.ElideRight
        }
        Switch {
            anchors { right: parent.right; rightMargin: 8; verticalCenter: parent.verticalCenter }
            id: sw
            checked: app.settingsMap[tg.settingKey] === true
            onToggled: tg.act ? tg.act(checked) : app.setSetting(tg.settingKey, checked)
            indicator: Rectangle {
                implicitWidth: 40; implicitHeight: 22; radius: 11
                y: parent.height / 2 - height / 2
                color: sw.checked ? theme.primary : theme.surfaceContainerHighest
                Rectangle {
                    x: sw.checked ? parent.width - width - 3 : 3
                    y: 3; width: 16; height: 16; radius: 8
                    color: sw.checked ? theme.onPrimary : theme.outline
                }
            }
        }
    }
    // A round icon button for the screenshot viewer.
    component Round: Rectangle {
        id: rb
        property string icon
        signal tapped()
        width: 48; height: 48; radius: 24
        color: rbHover.hovered ? Qt.alpha("white", 0.22) : Qt.alpha("white", 0.12)
        Icon { anchors.centerIn: parent; name: rb.icon; size: 22; color: "white" }
        HoverHandler { id: rbHover; cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: rb.tapped() }
    }
    // An L-shaped corner mark (the icon's corner); rotate it to frame any corner.
    // A soft L: one stroke with a rounded bend and round ends, like the logo's letters.
    // Drawn as the bottom-left corner; rotate it for the others.
    component CornerMark: Item {
        id: cm
        property color tone: "white"
        property int size: 30
        property real thick: 4
        readonly property real bend: size * 0.5
        width: size; height: size
        Shape {
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeColor: cm.tone
                strokeWidth: cm.thick
                fillColor: "transparent"
                capStyle: ShapePath.RoundCap
                joinStyle: ShapePath.RoundJoin
                startX: cm.thick / 2; startY: cm.thick / 2
                PathLine { x: cm.thick / 2; y: cm.size - cm.bend }
                PathArc { x: cm.bend; y: cm.size - cm.thick / 2; radiusX: cm.bend - cm.thick / 2; radiusY: cm.bend - cm.thick / 2; direction: PathArc.Counterclockwise }
                PathLine { x: cm.size - cm.thick / 2; y: cm.size - cm.thick / 2 }
            }
        }
    }

    // A small rounded label: optional store logo, text, optional accent colour.
    // One row of a small menu.
    component MenuRow: Rectangle {
        id: mr
        property string icon
        property string text
        property bool danger: false
        signal picked()
        width: parent ? parent.width : 220; height: 38; radius: 8
        color: mrHover.hovered ? app.theme.surfaceContainerHighest : "transparent"
        Icon { x: 12; anchors.verticalCenter: parent.verticalCenter; name: mr.icon; size: 16; color: mr.danger ? app.theme.error : app.theme.onSurfaceVariant }
        Text { x: 40; anchors.verticalCenter: parent.verticalCenter; text: mr.text; font.pixelSize: 13; color: mr.danger ? app.theme.error : app.theme.onSurface }
        HoverHandler { id: mrHover; cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: mr.picked() }
    }

    // A quiet top-bar button: icon + label, a count badge, an "on" state.
    component TopButton: Rectangle {
        id: tb
        property string icon
        property string label
        property int badge: 0
        property bool on: false
        signal picked()
        implicitWidth: tbRow.implicitWidth + 24; implicitHeight: 38; radius: 10
        color: on ? app.theme.primaryContainer : tbHover.hovered ? app.theme.surfaceContainerHigh : "transparent"
        Row {
            id: tbRow
            anchors.centerIn: parent
            spacing: 7
            Icon { anchors.verticalCenter: parent.verticalCenter; name: tb.icon; size: 16; color: tb.on ? app.theme.onPrimaryContainer : app.theme.onSurfaceVariant }
            Text { anchors.verticalCenter: parent.verticalCenter; text: tb.label; font.pixelSize: 13; color: tb.on ? app.theme.onPrimaryContainer : app.theme.onSurface }
            Rectangle { visible: tb.badge > 0; anchors.verticalCenter: parent.verticalCenter; width: 18; height: 18; radius: 9; color: app.theme.primary
                        Text { anchors.centerIn: parent; text: tb.badge; color: app.theme.onPrimary; font.pixelSize: 10; font.weight: Font.Bold } }
        }
        HoverHandler { id: tbHover; cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: tb.picked() }
    }

    // A filter chip (on / off).
    component Chip2: Rectangle {
        id: c2
        property string label
        property string icon: ""
        property bool on: false
        signal picked()
        height: 30; radius: 15
        width: c2row.implicitWidth + 24
        color: on ? app.theme.primaryContainer : c2Hover.hovered ? app.theme.surfaceContainerHigh : "transparent"
        border.width: on ? 0 : 1; border.color: app.theme.outlineVariant
        Row {
            id: c2row
            anchors.centerIn: parent
            spacing: 6
            Icon { visible: c2.icon !== ""; anchors.verticalCenter: parent.verticalCenter; name: c2.icon; size: 13
                   color: c2.on ? app.theme.onPrimaryContainer : app.theme.onSurfaceVariant }
            Text { anchors.verticalCenter: parent.verticalCenter; text: c2.label; font.pixelSize: 12
                   color: c2.on ? app.theme.onPrimaryContainer : app.theme.onSurfaceVariant }
        }
        HoverHandler { id: c2Hover; cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: c2.picked() }
    }

    // A home section's title: click to fold it away; arrows on hover move it up or down.
    component SectionHead: RowLayout {
        id: sh
        property string sid
        property string title
        property string icon: ""
        property string extra: ""
        signal extraPicked()
        width: parent ? parent.width : 0
        spacing: 8
        Icon { visible: sh.icon !== ""; name: sh.icon; size: 15; color: app.theme.primary }
        Text { text: sh.title; color: app.theme.onSurface; font.pixelSize: 15; font.weight: Font.DemiBold }
        Icon { name: win.homeFolded(sh.sid) ? "chevron-right" : "chevron-down"; size: 14; color: app.theme.outline }
        Item { Layout.fillWidth: true }
        Row {
            spacing: 2
            opacity: shHover.hovered ? 1 : 0
            visible: sh.sid !== "sales"  // the two movable sections only
            Behavior on opacity { NumberAnimation { duration: 120 } }
            Repeater {
                model: [{ i: "chevron-up", d: -1 }, { i: "chevron-down", d: 1 }]
                Rectangle {
                    required property var modelData
                    width: 24; height: 22; radius: 6
                    color: mvHover.hovered ? app.theme.surfaceContainerHigh : "transparent"
                    Icon { anchors.centerIn: parent; name: modelData.i; size: 14; color: app.theme.onSurfaceVariant }
                    HoverHandler { id: mvHover; cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: win.moveHome(sh.sid, modelData.d) }
                }
            }
        }
        Text {  // an extra, quiet action (Free on Epic: hide until the offers change)
            visible: sh.extra !== "" && shHover.hovered
            text: sh.extra; color: app.theme.primary; font.pixelSize: 12
            TapHandler { onTapped: sh.extraPicked() }
            HoverHandler { cursorShape: Qt.PointingHandCursor }
        }
        HoverHandler { id: shHover }
        TapHandler { onTapped: win.toggleHome(sh.sid) }
    }

    component Pill: Rectangle {
        id: pill
        readonly property var theme: app.theme
        property string label: ""
        property string store: ""
        property string dot: ""
        property bool accent: false
        height: 28
        radius: 14
        width: pillRow.implicitWidth + 24
        color: accent ? Qt.alpha(theme.primary, 0.18) : Qt.alpha(theme.surfaceContainerHighest, 0.9)
        border.width: accent ? 1 : 0
        border.color: Qt.alpha(theme.primary, 0.6)
        Row {
            id: pillRow
            anchors.centerIn: parent
            spacing: 7
            Rectangle {
                visible: pill.store === "" && pill.dot !== ""
                anchors.verticalCenter: parent.verticalCenter
                width: 9; height: 9; radius: 5
                color: pill.dot || "transparent"
            }
            StoreIcon {
                visible: pill.store !== ""
                anchors.verticalCenter: parent.verticalCenter
                size: 14; store: pill.store; color: pill.dot || "white"
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: pill.label
                color: theme.onSurface
                font.pixelSize: 12
                font.weight: pill.accent ? Font.DemiBold : Font.Normal
            }
        }
    }

    component Chip: Rectangle {
        id: chip
        readonly property var theme: app.theme
        property string label
        property bool active: false
        property string dot: ""
        property string store: ""
        property string icon: ""
        signal picked()
        implicitWidth: chipText.implicitWidth + (dot || icon ? 42 : 26)
        implicitHeight: 32
        radius: 16
        color: active ? theme.primaryContainer : chipHover.hovered ? theme.surfaceContainerHighest : theme.surfaceContainerHigh
        border.width: 1
        border.color: active ? theme.primary : theme.outlineVariant
        StoreIcon { visible: chip.dot !== ""; x: 11; anchors.verticalCenter: parent.verticalCenter; size: 14; store: chip.store; color: chip.dot || "transparent" }
        Icon {
            visible: chip.dot === "" && chip.icon !== ""
            x: 12; anchors.verticalCenter: parent.verticalCenter
            name: chip.icon; size: 15
            color: chip.active ? theme.onPrimaryContainer : theme.onSurfaceVariant
        }
        Text {
            id: chipText
            x: chip.dot || chip.icon ? 31 : 13
            anchors.verticalCenter: parent.verticalCenter
            text: chip.label
            color: chip.active ? theme.onPrimaryContainer : theme.onSurface
            font.pixelSize: 13
        }
        HoverHandler { id: chipHover; cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: chip.picked() }
    }

    KDialog {
        id: prefs
        objectName: "prefs"
        theme: win.theme
        heading: qsTr("Settings")
        headingIcon: "sliders-horizontal"
        width: Math.min(win.width - 60, 640)
        property int tab: 0
        onTabChanged: { prefsScroll.contentY = 0; if (!app.light) tabSwap.restart() }
        ParallelAnimation {
            id: tabSwap
            NumberAnimation { target: prefsScroll; property: "opacity"; from: 0; to: 1; duration: 220; easing.type: Easing.OutCubic }
            NumberAnimation { target: prefsSlide; property: "y"; from: 18; to: 0; duration: 260; easing.type: Easing.OutCubic }
        }
        // Search: matching options light up; the first page with a match opens; tabs show counts.
        property string query: ""
        property var counts: []
        function hitsIn(item) {
            let n = 0
            for (const c of item.children || []) {
                if (c.hit === true) n++
                n += hitsIn(c)
            }
            return n
        }
        function firstHit(item) {
            for (const c of item.children || []) {
                if (c.hit === true) return c
                const d = firstHit(c)
                if (d) return d
            }
            return null
        }
        onQueryChanged: Qt.callLater(function() {
            const stack = prefsStack.item
            if (!stack) return
            counts = query ? [...Array(stack.children.length).keys()].map(i => hitsIn(stack.children[i])) : []
            if (query && counts.length && !counts[tab]) {
                const i = counts.findIndex(n => n > 0)
                if (i >= 0) tab = i
            }
            Qt.callLater(function() {
                const hit = query ? firstHit(stack.children[tab]) : null
                if (hit) prefsScroll.contentY = Math.max(0, hit.mapToItem(stack, 0, 0).y - 20)
            })
        })
        onClosed: { query = ""; prefsFind.text = "" }
        property bool wasOpened: false
        onAboutToShow: wasOpened = true

        contentItem: ColumnLayout {
            spacing: 18
            KField {
                id: prefsFind
                theme: win.theme
                Layout.fillWidth: true
                iconName: "search"
                placeholderText: qsTr("Find a setting (e.g. proton, cover, sync)")
                onTextChanged: prefs.query = text.trim().toLowerCase()
            }
            Flow {  // wraps when the tab names are long (translations)
                Layout.fillWidth: true
                spacing: 8
                Repeater {
                    model: [{ name: qsTr("Appearance"), icon: "eye" }, { name: qsTr("Games & Proton"), icon: "gamepad-2" },
                            { name: qsTr("People & sync"), icon: "user-round" }, { name: qsTr("Library"), icon: "library" },
                            { name: qsTr("Advanced"), icon: "sliders-horizontal" }]
                    Chip {
                        required property var modelData
                        required property int index
                        label: modelData.name + (prefs.query && prefs.counts.length ? "  " + (prefs.counts[index] || 0) : "")
                        opacity: prefs.query && prefs.counts.length && !prefs.counts[index] ? 0.45 : 1
                        icon: modelData.icon
                        active: prefs.tab === index
                        onPicked: prefs.tab = index
                    }
                }
            }

            // The pages scroll when they are taller than the window.
            Flickable {
                id: prefsScroll
                transform: Translate { id: prefsSlide }
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(prefsStack.implicitHeight, win.height - 220)
                contentHeight: prefsStack.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: KScrollBar { }
                // The pages are built the first time Settings opens.
                Loader {
                    id: prefsStack
                    active: prefs.wasOpened
                    width: prefsScroll.width - 12
                    sourceComponent: StackLayout {
                        currentIndex: prefs.tab

                        // ---- Appearance
                        ColumnLayout {
                            spacing: 16
                            Row2 {
                                label: qsTr("Theme")
                                hint: qsTr("Follow wallpaper picks Cornerplay's colours from your desktop wallpaper and changes with it. Works with Ryoku, GNOME, KDE, Xfce, Cinnamon, MATE, Hyprland (hyprpaper, swww) and Sway.")
                                Flow {
                                    Layout.fillWidth: true
                                    spacing: 8
                                    Chip {
                                        label: qsTr("Follow wallpaper")
                                        active: app.settingsMap.theme_mode === "ryoku"
                                        onPicked: app.setSetting("theme_mode", "ryoku")
                                    }
                                    Repeater {
                                        model: app.themePresets
                                        Chip {
                                            required property string modelData
                                            label: modelData
                                            active: app.settingsMap.theme_mode === modelData
                                            onPicked: app.setSetting("theme_mode", modelData)
                                        }
                                    }
                                    Chip {
                                        label: qsTr("Custom")
                                        active: app.settingsMap.theme_mode === "custom"
                                        onPicked: app.setCustomColor("theme_accent", win.theme.primary)
                                    }
                                }
                            }
                            Row2 {
                                label: qsTr("Accent colour")
                                Swatches {
                                    theme: win.theme
                                    Layout.fillWidth: true
                                    choices: app.accentChoices
                                    value: win.theme.primary
                                    onPicked: colour => app.setCustomColor("theme_accent", colour)
                                }
                            }
                            Row2 {
                                label: qsTr("Background colour")
                                hint: qsTr("Picking a colour switches to a custom theme; text and panel shades are worked out from these two.")
                                Swatches {
                                    theme: win.theme
                                    Layout.fillWidth: true
                                    choices: app.backgroundChoices
                                    value: win.theme.background
                                    onPicked: colour => app.setCustomColor("theme_bg", colour)
                                }
                            }
                            Row2 {
                                label: qsTr("Cover size")
                                KSlider {
                                    theme: win.theme; Layout.fillWidth: true
                                    from: 130; to: 320; stepSize: 2
                                    value: app.settingsMap.card_size
                                    onMoved: app.setSetting("card_size", value)
                                }
                            }
                            RowLayout {
                                spacing: 10
                                Row2 {
                                    label: qsTr("Interface size (text and buttons)")
                                    hint: qsTr("Applies after a restart.")
                                    KCombo {
                                        theme: win.theme; Layout.fillWidth: true
                                        model: [{ label: qsTr("Automatic (bigger on large unscaled screens)"), value: 0.0 },
                                                { label: qsTr("Normal (100%)"), value: 1.0 }, { label: qsTr("Larger (115%)"), value: 1.15 },
                                                { label: qsTr("Larger still (130%)"), value: 1.3 }, { label: "150%", value: 1.5 },
                                                { label: qsTr("200% (4K at 100%)"), value: 2.0 }]
                                        Component.onCompleted: select(app.settingsMap.ui_scale || 0.0)
                                        onActivated: app.setSetting("ui_scale", currentValue)
                                    }
                                }
                                KButton { theme: win.theme; Layout.alignment: Qt.AlignBottom; text: qsTr("Restart now"); iconName: "refresh-cw"; onClicked: app.restartApp() }
                            }
                            Row2 {
                                label: qsTr("Language")
                                hint: qsTr("Applies after a restart.")
                                KCombo {
                                    theme: win.theme; Layout.fillWidth: true
                                    model: [{ label: qsTr("Automatic (the system's)"), value: "" }].concat(app.languages)
                                    Component.onCompleted: select(app.settingsMap.language || "")
                                    onActivated: app.setSetting("language", currentValue)
                                }
                            }
                            Row2 {
                                label: qsTr("Cover shadows")
                                KCombo {
                                    theme: win.theme; Layout.fillWidth: true
                                    model: [{ label: qsTr("None (flat)"), value: "none" }, { label: qsTr("Soft"), value: "soft" }, { label: qsTr("Deep"), value: "deep" }]
                                    Component.onCompleted: select(app.settingsMap.card_shadow || "soft")
                                    onActivated: app.setSetting("card_shadow", currentValue)
                                }
                            }
                            Toggle { visible: app.settingsMap.theme_mode === "ryoku"; label: qsTr("Show the wallpaper behind Cornerplay (blurred)"); settingKey: "wallpaper_backdrop" }
                            Toggle { label: qsTr("Play a game's trailer inside its cover while pointed at"); settingKey: "hover_trailers" }
                            Toggle { label: qsTr("Warmer colours in the evening and at night"); settingKey: "evening_warmth" }
                            Toggle { label: qsTr("TV mode: covers reflected on the shelf"); settingKey: "tv_reflection" }
                            Toggle { label: qsTr("TV mode: start-up animation and chime"); settingKey: "tv_intro" }
                            KButton {
                                theme: win.theme
                                text: app.settingsMap.card_size >= 250 ? qsTr("Back to normal tiles") : qsTr("Large tiles (touchscreens)")
                                iconName: "layout-grid"
                                onClicked: app.setSetting("card_size", app.settingsMap.card_size >= 250 ? 196 : 270)
                            }
                            Row2 {
                                label: qsTr("Corner roundness")
                                KSlider {
                                    theme: win.theme; Layout.fillWidth: true
                                    from: 0; to: 28; stepSize: 1
                                    value: app.settingsMap.card_radius
                                    onMoved: app.setSetting("card_radius", value)
                                }
                            }
                            Toggle { label: qsTr("Show the store on a cover when pointed at"); settingKey: "show_badges" }
                            Toggle { label: qsTr("Always show game titles"); settingKey: "show_titles" }
                            Toggle { label: qsTr("Dim games that are not installed"); settingKey: "dim_uninstalled" }
                        Toggle { visible: typeof canPlayVideo !== "undefined" && canPlayVideo; label: qsTr("TV mode: play the focused game's trailer (muted)"); settingKey: "tv_trailers" }
                        Toggle { label: qsTr("TV mode: animated covers and banners (SteamGridDB key needed; only when plugged in)"); settingKey: "tv_animated" }
                        Toggle { label: qsTr("TV mode: soft sounds when moving and choosing"); settingKey: "tv_sounds" }
                        Toggle { label: qsTr("Show the ProtonDB rating on a cover when pointed at"); settingKey: "show_protondb" }
                        Row2 {
                            label: qsTr("Retro games (ROM folders)")
                            hint: (app.settingsMap.rom_dirs || []).length
                                  ? (app.settingsMap.rom_dirs || []).join("  ·  ") + (app.retroProblem ? "  —  " + app.retroProblem : "")
                                  : "Add a folder with ROMs (a folder per system works best: snes, psx, gba ...). They play in RetroArch, with box art, playtime and TV mode."
                            RowLayout {
                                spacing: 8
                                KButton { theme: win.theme; iconName: "folder-open"; text: qsTr("Add folder"); onClicked: romDest.open() }
                                KButton { theme: win.theme; text: qsTr("Clear"); visible: (app.settingsMap.rom_dirs || []).length > 0
                                          onClicked: { app.setSetting("rom_dirs", []); app.refresh("retro") } }
                            }
                        }
                        Toggle { label: qsTr("Show games from my Steam and GOG wishlists that are on sale"); settingKey: "wishlist_sales" }
                        Row2 {
                            visible: !!app.settingsMap.wishlist_sales
                            label: qsTr("Country for store prices")
                            hint: qsTr("Two letters, like AU or RO. Empty: your GOG account's country, else your system's.")
                            KField {
                                theme: win.theme; Layout.preferredWidth: 90
                                placeholderText: qsTr("Auto")
                                maximumLength: 2
                                text: app.settingsMap.store_country
                                onEditingFinished: { app.setSetting("store_country", text.trim().toUpperCase()); app.refresh() }
                            }
                        }
                        Row2 {
                            visible: !!app.settingsMap.wishlist_sales
                            label: qsTr("Best price on any store (IsThereAnyDeal)")
                            hint: qsTr("With a free IsThereAnyDeal API key, each wishlist game shows its cheapest deal on any store (Steam, GOG, Epic, Humble, Fanatical and more) and Cornerplay tells you when one is at least as much off as you choose here, or at its lowest price ever. Get one free: sign in at isthereanydeal.com and register an app (the Get a key button).")
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                KField {
                                    theme: win.theme; Layout.fillWidth: true
                                    placeholderText: qsTr("API key")
                                    echoMode: TextInput.Password
                                    text: app.settingsMap.itad_key
                                    onEditingFinished: if (text.trim() !== app.settingsMap.itad_key) { app.setSetting("itad_key", text.trim()); app.refresh() }
                                }
                                KButton { theme: win.theme; text: qsTr("Get a key"); iconName: "external-link"
                                          onClicked: app.openUrl("https://isthereanydeal.com/apps/my/") }
                            }
                            RowLayout {
                                visible: !!app.settingsMap.itad_key
                                spacing: 8
                                Text { text: qsTr("Tell me at"); color: theme.onSurface; font.pixelSize: 13 }
                                KField {
                                    theme: win.theme; Layout.preferredWidth: 60
                                    text: String(app.settingsMap.deal_alert_cut)
                                    validator: IntValidator { bottom: 1; top: 100 }
                                    onEditingFinished: app.setSetting("deal_alert_cut", parseInt(text) || 50)
                                }
                                Text { text: qsTr("% off, or at the lowest price ever"); color: theme.onSurface; font.pixelSize: 13 }
                            }
                        }
                        }

                        // ---- Games & Proton
                        ColumnLayout {
                            spacing: 16
                            Row2 {
                                label: qsTr("Default Proton version")
                                hint: qsTr("Used for Epic, GOG, Amazon and Battle.net games; each game can pick its own under Options. Steam games use the version set inside Steam.")
                                KCombo {
                                    id: protonBox
                                    theme: win.theme; Layout.fillWidth: true
                                    model: app.protonVersions
                                    onModelChanged: select(app.settingsMap.proton)
                                    Component.onCompleted: select(app.settingsMap.proton)
                                    onActivated: app.setSetting("proton", currentValue)
                                }
                            }
                            // Proton-CachyOS: tuned builds from CachyOS (faster v3 build on newer CPUs).
                            Rectangle {
                                Layout.fillWidth: true
                                implicitHeight: cachyRow.implicitHeight + 28
                                radius: 12
                                color: theme.surfaceContainerHigh
                                Component.onCompleted: app.checkCachy()
                                ColumnLayout {
                                    id: cachyRow
                                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 14 }
                                    spacing: 8
                                    RowLayout {
                                        spacing: 10
                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 2
                                            Text { text: qsTr("Proton-CachyOS"); color: theme.onSurface; font.pixelSize: 13; font.weight: Font.DemiBold }
                                            Text {
                                                Layout.fillWidth: true
                                                wrapMode: Text.WordWrap
                                                font.pixelSize: 12
                                                color: app.cachyStatus.error ? theme.error : theme.onSurfaceVariant
                                                text: app.cachyStatus.error ? app.cachyStatus.error
                                                      : app.cachyStatus.busy ? "Downloading " + Math.floor(app.cachyStatus.progress) + "%  (about 400 MB)"
                                                      : (app.cachyStatus.installed ? "Installed: " + app.cachyStatus.installed.replace("proton-cachyos-", "") : "Performance-tuned Proton from CachyOS; often faster. Not downloaded yet")
                                                        + (app.cachyStatus.latest ? (app.cachyStatus.upToDate ? "  ·  up to date" : "  ·  newest: " + app.cachyStatus.latest) : "")
                                            }
                                        }
                                        KButton {
                                            theme: win.theme
                                            primary: !app.cachyStatus.upToDate
                                            enabled: !app.cachyStatus.busy
                                            text: app.cachyStatus.upToDate ? qsTr("Check again") : qsTr("Download latest")
                                            onClicked: app.cachyStatus.upToDate ? app.checkCachy() : app.downloadCachy()
                                        }
                                    }
                                    Rectangle {
                                        visible: !!app.cachyStatus.busy
                                        Layout.fillWidth: true
                                        height: 5; radius: 3
                                        color: theme.surfaceContainerHighest
                                        Rectangle { height: parent.height; radius: 3; color: theme.primary; width: parent.width * (app.cachyStatus.progress || 0) / 100 }
                                    }
                                }
                            }
                            Rectangle {
                                Layout.fillWidth: true
                                implicitHeight: geCol.implicitHeight + 28
                                radius: 12
                                color: theme.surfaceContainerHigh
                                Component.onCompleted: app.checkGe()
                                ColumnLayout {
                                    id: geCol
                                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 14 }
                                    spacing: 8
                                    RowLayout {
                                        spacing: 10
                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 2
                                            Text { text: qsTr("GE-Proton"); color: theme.onSurface; font.pixelSize: 13; font.weight: Font.DemiBold }
                                            Text {
                                                Layout.fillWidth: true
                                                wrapMode: Text.WordWrap
                                                font.pixelSize: 12
                                                color: app.geStatus.error ? theme.error : theme.onSurfaceVariant
                                                text: app.geStatus.error ? app.geStatus.error
                                                      : app.geStatus.busy ? "Downloading " + Math.floor(app.geStatus.progress) + "%  (about 570 MB)"
                                                      : (app.geStatus.installed ? "Installed: " + app.geStatus.installed.replace("-x86_64", "") : "Not downloaded yet")
                                                        + (app.geStatus.latest ? (app.geStatus.upToDate ? "  ·  up to date" : "  ·  newest: " + app.geStatus.latest) : "")
                                            }
                                        }
                                        KButton {
                                            theme: win.theme
                                            primary: !app.geStatus.upToDate
                                            enabled: !app.geStatus.busy
                                            text: app.geStatus.upToDate ? qsTr("Check again") : qsTr("Download latest")
                                            onClicked: app.geStatus.upToDate ? app.checkGe() : app.downloadGe()
                                        }
                                    }
                                    Rectangle {
                                        visible: !!app.geStatus.busy
                                        Layout.fillWidth: true
                                        height: 5; radius: 3
                                        color: theme.surfaceContainerHighest
                                        Rectangle { height: parent.height; radius: 3; color: theme.primary; width: parent.width * (app.geStatus.progress || 0) / 100 }
                                    }
                                    Rectangle { Layout.fillWidth: true; height: 1; color: theme.outlineVariant }
                                    RowLayout {
                                        spacing: 10
                                        Text {
                                            Layout.fillWidth: true
                                            wrapMode: Text.WordWrap
                                            font.pixelSize: 12
                                            color: theme.onSurfaceVariant
                                            text: qsTr("Steam's own Proton builds (Proton Experimental, Proton 10…) are listed above once Steam has downloaded them.")
                                        }
                                        KButton { theme: win.theme; text: qsTr("Get from Steam"); onClicked: app.getSteamProton() }
                                        KButton { theme: win.theme; text: qsTr("Rescan"); onClicked: app.rescanProtons() }
                                    }
                                }
                            }
                            Toggle { label: qsTr("MangoHud overlay"); settingKey: "mangohud" }
                            Toggle { label: qsTr("Feral GameMode"); settingKey: "gamemode" }
                            Toggle { label: qsTr("FPS counter in games"); settingKey: "show_fps" }
                            Row2 {
                                label: qsTr("Gamescope for every game")
                                hint: app.hasGamescope
                                      ? "Runs Epic, GOG, Amazon and added games inside Valve's gamescope: a clean full-screen window at your screen's resolution, or drawn smaller and upscaled with FSR for more frames. Each game can choose its own under Options. Steam games: use Steam's launch options."
                                      : "gamescope is not installed (on Arch: sudo pacman -S gamescope). Until it is, games start without it."
                                KCombo {
                                    theme: win.theme; Layout.fillWidth: true
                                    model: [{ label: qsTr("Off"), value: "" }, { label: qsTr("Full screen at screen resolution"), value: "fullscreen" },
                                            { label: qsTr("FSR upscaling (draws at 2/3 size)"), value: "fsr" }]
                                    Component.onCompleted: select(app.settingsMap.gamescope || "")
                                    onActivated: app.setSetting("gamescope", currentValue)
                                }
                            }
                            Toggle { label: qsTr("HDR in gamescope (HDR screen and compositor needed)"); settingKey: "gamescope_hdr"; visible: app.hasGamescope }
                            Toggle { label: qsTr("GOG: install the Linux version when a game has one (no Proton needed)"); settingKey: "gog_native" }
                            Row2 {
                                label: qsTr("Performance profile for every game")
                                hint: qsTr("Battery saver caps at 30 fps and Balanced at 60, both with FSR upscaling. Each game can choose its own under Options. Steam games use Steam's settings.")
                                KCombo {
                                    theme: win.theme; Layout.fillWidth: true
                                    model: [{ label: qsTr("No change"), value: "" }, { label: qsTr("Battery saver (30 fps)"), value: "battery" },
                                            { label: qsTr("Balanced (60 fps)"), value: "balanced" }, { label: qsTr("Max quality (no cap)"), value: "quality" }]
                                    Component.onCompleted: select(app.settingsMap.perf || "")
                                    onActivated: app.setSetting("perf", currentValue)
                                }
                            }
                        }

                        // ---- People & sync
                        ColumnLayout {
                            spacing: 16
                            Text {
                                Layout.fillWidth: true
                                wrapMode: Text.WordWrap
                                color: theme.onSurfaceVariant; font.pixelSize: 13
                                text: qsTr("Each person gets their own favourites, collections, statuses, stars, notes and play stats. Games, sign-ins and settings are shared. Switch from the name at the top of the sidebar.")
                            }
                            Repeater {
                                model: app.profiles
                                Rectangle {
                                    required property string modelData
                                    Layout.fillWidth: true
                                    height: 48; radius: 12
                                    color: theme.surfaceContainerHigh
                                    Rectangle {
                                        x: 12; anchors.verticalCenter: parent.verticalCenter
                                        width: 28; height: 28; radius: 14
                                        color: modelData === app.profile ? theme.primary : theme.surfaceContainerHighest
                                        Text { anchors.centerIn: parent; text: modelData.charAt(0).toUpperCase(); font.pixelSize: 13; font.weight: Font.Bold
                                               color: modelData === app.profile ? theme.onPrimary : theme.onSurface }
                                    }
                                    Text { x: 52; anchors.verticalCenter: parent.verticalCenter; text: modelData + (modelData === app.profile ? qsTr("  (now)") : "")
                                           color: theme.onSurface; font.pixelSize: 14 }
                                    Row {
                                        anchors { right: parent.right; rightMargin: 8; verticalCenter: parent.verticalCenter }
                                        spacing: 6
                                        KButton { theme: win.theme; visible: modelData !== app.profile; text: qsTr("Switch"); onClicked: app.switchProfile(modelData) }
                                        KButton { theme: win.theme; visible: app.profiles.length > 1; danger: true; iconName: "trash-2"; text: ""
                                                  onClicked: app.removeProfile(modelData) }
                                    }
                                }
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                KField { id: newPerson; theme: win.theme; Layout.fillWidth: true; placeholderText: qsTr("Add a person (name)")
                                         Keys.onReturnPressed: { if (app.addProfile(text)) text = "" } }
                                KButton { theme: win.theme; text: qsTr("Add"); iconName: "plus"; enabled: newPerson.text.trim() !== ""
                                          onClicked: { if (app.addProfile(newPerson.text)) newPerson.text = "" } }
                            }
                            Rectangle { Layout.fillWidth: true; height: 1; color: theme.outlineVariant }
                            Row2 {
                                label: qsTr("Sync with your other PCs")
                                hint: qsTr("Pick a folder that Syncthing, Nextcloud, Dropbox or similar already keeps in step between your PCs (and the Steam Deck). Cornerplay keeps everyone's favourites, collections, statuses, notes and playtime in a Cornerplay folder inside it, merged game by game. Your games themselves are not copied.")
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 8
                                    KField { id: syncField; theme: win.theme; Layout.fillWidth: true; placeholderText: qsTr("Not syncing")
                                             text: app.syncState.dir || ""
                                             onEditingFinished: if (text.trim() !== (app.syncState.dir || "")) app.setSyncDir(text.trim()) }
                                    KButton { theme: win.theme; text: qsTr("Choose…"); iconName: "folder-open"; onClicked: syncDest.open() }
                                }
                            }
                            Rectangle { Layout.fillWidth: true; height: 1; color: theme.outlineVariant }
                            Row2 {
                                label: qsTr("Back up Cornerplay")
                                hint: qsTr("One file with your settings, people, favourites, collections, notes and playtime: for a new PC, or before trying things. Store sign-ins are not in it (sign in again on the new PC).")
                                RowLayout {
                                    spacing: 8
                                    KButton { theme: win.theme; text: qsTr("Save a backup…"); iconName: "download"; onClicked: backupDest.open() }
                                    KButton { theme: win.theme; text: qsTr("Restore…"); iconName: "refresh-cw"; onClicked: restoreFile.open() }
                                }
                            }
                            RowLayout {
                                visible: !!app.syncState.dir
                                spacing: 10
                                KButton { theme: win.theme; text: app.syncState.busy ? qsTr("Syncing…") : qsTr("Sync now"); iconName: "refresh-cw"
                                          enabled: !app.syncState.busy; onClicked: app.syncPersonal() }
                                KButton { theme: win.theme; text: qsTr("Stop syncing"); onClicked: app.setSyncDir("") }
                                Text { text: app.syncState.error ? qsTr("Last sync failed: ") + app.syncState.error
                                             : app.syncState.when ? "Last synced " + app.syncState.when : ""
                                       color: app.syncState.error ? theme.error : theme.onSurfaceVariant; font.pixelSize: 12 }
                            }
                            Rectangle { Layout.fillWidth: true; height: 1; color: theme.outlineVariant; visible: app.inFlatpak }
                            Row2 {
                                visible: app.inFlatpak
                                label: qsTr("Bring over from the regular install")
                                hint: qsTr("Copies the library, settings and store sign-ins of Cornerplay installed outside Flatpak on this PC (the .run installer or the AUR package). What the Flatpak has now is kept aside, and the other install is left as it is.")
                                KButton { theme: win.theme; text: app.hostImport.busy ? qsTr("Bringing over…") : qsTr("Bring over")
                                          iconName: "download"; enabled: !app.hostImport.busy; onClicked: app.importFromHost() }
                            }
                        }

                        // ---- Library
                        ColumnLayout {
                            spacing: 16
                            Row2 {
                                label: qsTr("Download speed limit")
                                hint: qsTr("For Epic, GOG and Amazon downloads, so a big game leaves room for everything else on your internet. Empty: as fast as it goes. Steam has its own limit in its Downloads settings.")
                                RowLayout {
                                    spacing: 8
                                    KField {
                                        theme: win.theme
                                        Layout.preferredWidth: 100
                                        placeholderText: qsTr("none")
                                        text: app.settingsMap.download_limit > 0 ? String(app.settingsMap.download_limit) : ""
                                        validator: DoubleValidator { bottom: 0; top: 10000; decimals: 1; notation: DoubleValidator.StandardNotation }
                                        onEditingFinished: app.setSetting("download_limit", parseFloat(text.replace(",", ".")) || 0)
                                    }
                                    Text { text: "MB/s"; color: theme.onSurfaceVariant; font.pixelSize: 13 }
                                }
                            }
                            Row2 {
                                label: qsTr("Games folder")
                                hint: qsTr("Where Epic, GOG and Amazon games and all Proton prefixes are stored. Steam keeps using its own libraries.")
                                KField {
                                    theme: win.theme; Layout.fillWidth: true
                                    text: app.settingsMap.games_dir
                                    onEditingFinished: app.setSetting("games_dir", text.trim())
                                }
                            }
                            Rectangle {
                                Layout.fillWidth: true
                                implicitHeight: steamCol.implicitHeight + 28
                                radius: 12
                                color: theme.surfaceContainerHigh
                                readonly property var st: app.steamShortcut
                                ColumnLayout {
                                    id: steamCol
                                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 14 }
                                    spacing: 8
                                    RowLayout {
                                        spacing: 10
                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 2
                                            Text { text: qsTr("Your games in Steam & Game Mode"); color: theme.onSurface; font.pixelSize: 13; font.weight: Font.DemiBold }
                                            Text {
                                                Layout.fillWidth: true
                                                wrapMode: Text.WordWrap
                                                font.pixelSize: 12
                                                color: theme.onSurfaceVariant
                                                readonly property var st: parent.parent.parent.parent.st
                                                text: st.busy ? qsTr("Working… ") + (st.progress || "")
                                                      : !st.steam ? "Steam isn't installed or hasn't been signed in to yet."
                                                      : st.accounts === 0 ? "Sign in to Steam once, then come back here."
                                                      : st.games === 0 ? "No installed Epic, GOG, Amazon or Battle.net games yet."
                                                      : st.inSync ? "All " + st.games + " installed games are in Steam with cover, banner, background and logo."
                                                      : st.gamesInSteam + " of " + st.games + " installed games are in Steam. Adding them gives each its cover, banner, background and logo in Game Mode."
                                                        + (st.running ? " Steam is closed and reopened to do this." : "")
                                            }
                                        }
                                        KButton {
                                            theme: win.theme
                                            readonly property var st: parent.parent.parent.st
                                            primary: !st.inSync
                                            enabled: !st.busy && st.accounts > 0 && st.games > 0 && !st.gameMode
                                            text: st.inSync ? qsTr("Refresh in Steam") : qsTr("Add games to Steam")
                                            onClicked: app.addGamesToSteam()
                                        }
                                    }
                                    Toggle { label: qsTr("Keep installed games in Steam automatically"); settingKey: "steam_games" }
                                    Text {
                                        Layout.fillWidth: true
                                        wrapMode: Text.WordWrap
                                        font.pixelSize: 11
                                        color: theme.outline
                                        text: qsTr("Automatic adds newly installed games and removes uninstalled or hidden ones whenever Steam is closed; it never closes Steam by itself. Games bought on Steam are already there.")
                                    }
                                    Rectangle { Layout.fillWidth: true; height: 1; color: theme.outlineVariant }
                                    RowLayout {
                                        Text {
                                            Layout.fillWidth: true
                                            wrapMode: Text.WordWrap
                                            font.pixelSize: 12
                                            color: theme.onSurfaceVariant
                                            text: qsTr("Also add Cornerplay itself, so the whole library opens in TV mode from Game Mode.")
                                        }
                                        KButton {
                                            theme: win.theme
                                            readonly property var st: parent.parent.parent.st
                                            enabled: !st.busy && st.accounts > 0 && !st.gameMode
                                            text: qsTr("Add Cornerplay")
                                            onClicked: app.addToSteam()
                                        }
                                    }
                                }
                                Component.onCompleted: app.checkSteamShortcut()
                            }
                            Toggle { label: qsTr("Show a game owned on several stores only once"); settingKey: "merge_duplicates" }
                            Toggle { label: qsTr("Back up a game's saves before it starts (keeps the last 5; a game's More > Save backups to restore)"); settingKey: "save_backups" }
                            Toggle { label: qsTr("Update Epic, GOG and Amazon games overnight (plugged in, not on a metered connection, while Cornerplay is open)"); settingKey: "auto_update" }
                            RowLayout {
                                visible: !!app.settingsMap.auto_update
                                spacing: 10
                                Text { text: qsTr("Between"); color: theme.onSurfaceVariant; font.pixelSize: 13 }
                                KCombo { theme: win.theme; Layout.preferredWidth: 110
                                         model: [...Array(24).keys()].map(h => ({ label: (h < 10 ? "0" : "") + h + ":00", value: h }))
                                         Component.onCompleted: select(app.settingsMap.auto_update_from)
                                         onActivated: app.setSetting("auto_update_from", currentValue) }
                                Text { text: "and"; color: theme.onSurfaceVariant; font.pixelSize: 13 }
                                KCombo { theme: win.theme; Layout.preferredWidth: 110
                                         model: [...Array(24).keys()].map(h => ({ label: (h < 10 ? "0" : "") + h + ":00", value: h }))
                                         Component.onCompleted: select(app.settingsMap.auto_update_to)
                                         onActivated: app.setSetting("auto_update_to", currentValue) }
                            }
                            Row2 {
                                label: ""
                                hint: qsTr("Epic and GOG saves are downloaded before you play and uploaded when the game closes. Steam and Battle.net sync saves in their own apps; Amazon has no cloud saves.")
                                Toggle { label: qsTr("Sync cloud saves"); settingKey: "cloud_saves" }
                            }
                            Row2 {
                                label: qsTr("Steam Web API key (optional)")
                                hint: qsTr("Without a key Cornerplay shows the Steam games installed on this PC. With one it also lists everything you own. Get a key at <a href='https://steamcommunity.com/dev/apikey'>steamcommunity.com/dev/apikey</a>.")
                                KField {
                                    theme: win.theme; Layout.fillWidth: true
                                    echoMode: TextInput.PasswordEchoOnEdit
                                    text: app.settingsMap.steam_api_key
                                    onEditingFinished: { app.setSetting("steam_api_key", text.trim()); app.refresh("steam") }
                                }
                            }
                            Row2 {
                                label: qsTr("Artwork")
                                hint: qsTr("Covers follow the stores' current art: Steam's is checked every 2 days, GOG's every week, Epic's game data every week. This fetches everything again now.")
                                KButton {
                                    theme: win.theme
                                    iconName: "refresh-cw"
                                    text: qsTr("Refresh artwork now")
                                    enabled: !app.refreshing
                                    onClicked: app.refreshArtwork()
                                }
                            }
                            Row2 {
                                label: qsTr("SteamGridDB API key (optional)")
                                hint: qsTr("Games without box art are matched by title against Steam's store. A SteamGridDB key also finds art for games Steam does not sell: <a href='https://www.steamgriddb.com/profile/preferences/api'>steamgriddb.com/profile/preferences/api</a>.")
                                KField {
                                    theme: win.theme; Layout.fillWidth: true
                                    echoMode: TextInput.PasswordEchoOnEdit
                                    text: app.settingsMap.steamgriddb_key
                                    onEditingFinished: { app.setSetting("steamgriddb_key", text.trim()); app.refresh() }
                                }
                            }
                            Row2 {
                                label: qsTr("IGDB time to beat (optional)")
                                hint: qsTr("Shows how long a game takes (main story, with extras, 100%) on its page. Make a free app at <a href='https://dev.twitch.tv/console/apps'>dev.twitch.tv/console/apps</a> (OAuth redirect: http://localhost, category: Application Integration, client type: Confidential) and paste its Client ID and a new secret.")
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 8
                                    KField {
                                        theme: win.theme; Layout.fillWidth: true
                                        placeholderText: qsTr("Client ID")
                                        text: app.settingsMap.igdb_client_id
                                        onEditingFinished: app.setSetting("igdb_client_id", text.trim())
                                    }
                                    KField {
                                        theme: win.theme; Layout.fillWidth: true
                                        placeholderText: qsTr("Client secret")
                                        echoMode: TextInput.PasswordEchoOnEdit
                                        text: app.settingsMap.igdb_client_secret
                                        onEditingFinished: app.setSetting("igdb_client_secret", text.trim())
                                    }
                                }
                            }
                        }

                        // ---- Advanced
                        ColumnLayout {
                            spacing: 16
                            Text {
                                Layout.fillWidth: true
                                wrapMode: Text.WordWrap
                                color: theme.onSurfaceVariant; font.pixelSize: 13
                                text: qsTr("Things most people never need to change.")
                            }
                            Toggle { label: qsTr("Show what I play on Discord (Epic, GOG, Amazon and added games)"); settingKey: "discord_presence" }
                            Row2 {
                                visible: !!app.settingsMap.discord_presence
                                label: qsTr("Discord application ID")
                                hint: qsTr("Discord shows Steam games by itself. For the others, make a free application named Cornerplay at <a href='https://discord.com/developers/applications'>discord.com/developers/applications</a> and paste its Application ID. The desktop Discord app must be open; nothing is sent anywhere else.")
                                KField {
                                    theme: win.theme; Layout.fillWidth: true
                                    placeholderText: "e.g. 1234567890123456789"
                                    text: app.settingsMap.discord_app_id
                                    onEditingFinished: app.setSetting("discord_app_id", text.trim())
                                }
                            }
                            Row2 {
                                label: qsTr("Performance")
                                hint: qsTr("Light turns off rounded-cover effects, blur and animations so older PCs stay smooth. Automatic picks Light on PCs with 2 or fewer CPU cores, under 6 GB of memory, or no graphics acceleration.")
                                KCombo {
                                    id: perfBox
                                    theme: win.theme; Layout.fillWidth: true
                                    model: [{ label: qsTr("Automatic (now: ") + (app.light ? qsTr("Light") : qsTr("Full")) + ")", value: "auto" },
                                            { label: qsTr("Full effects"), value: "full" }, { label: qsTr("Light, for older PCs"), value: "light" }]
                                    Component.onCompleted: select(app.settingsMap.performance)
                                    onActivated: app.setSetting("performance", currentValue)
                                }
                            }
                            Row2 {
                                label: qsTr("Or a custom Proton folder")
                                KField {
                                    theme: win.theme; Layout.fillWidth: true
                                    placeholderText: qsTr("/path/to/a/Proton/folder")
                                    text: app.settingsMap.proton.startsWith("/") || app.settingsMap.proton.startsWith("~") ? app.settingsMap.proton : ""
                                    onEditingFinished: if (text.trim() !== "") app.setSetting("proton", text.trim())
                                }
                            }
                            Toggle { label: qsTr("Keep each game's shader cache (less stutter after the first run)"); settingKey: "shader_cache" }
                            Row2 {
                                label: qsTr("Environment variables for every game")
                                hint: qsTr("Space separated, for example: DXVK_HUD=fps PROTON_ENABLE_WAYLAND=1. Each game can override all of this from its Options button.")
                                KField {
                                    theme: win.theme; Layout.fillWidth: true
                                    placeholderText: qsTr("KEY=value KEY2=value")
                                    text: app.settingsMap.env
                                    onEditingFinished: app.setSetting("env", text.trim())
                                }
                            }
                            Toggle { label: qsTr("Check for new Cornerplay versions (once a day)"); settingKey: "update_check" }
                            Toggle { visible: app.trayAvailable; label: qsTr("Step aside into the tray while a game runs"); settingKey: "tray_while_playing" }
                            Toggle { visible: app.trayAvailable; label: qsTr("Keep running in the tray when the window is closed"); settingKey: "close_to_tray" }
                            Toggle { label: qsTr("Start with the PC (in the tray)"); settingKey: "start_with_pc"
                                     act: (on) => app.setStartWithPc(on) }
                        }

                    }
                }
            }
        }
    }

    // -------------------------------------------------------------------- per-game options
    KDialog {
        id: gameOpts
        objectName: "gameOpts"
        theme: win.theme
        property string key: ""
        property var game: ({})
        property var opts: ({})
        property var steamProton: ({ choices: [], current: "" })
        readonly property bool compat: ["epic", "gog", "amazon", "custom", "itch"].includes(game.store) || key === "battlenet:battlenet-app"
        // Runs without Proton: a GOG Linux version, or a Linux program added by hand.
        readonly property bool runsNative: game.platform === "linux"
        heading: qsTr("Options · ") + (game.title || "")
        width: Math.min(win.width - 60, 600)
        function show(k) {
            key = k
            game = app.game(k)
            opts = app.gameOptions(k)
            optProton.select(opts.proton === undefined ? "default" : opts.proton)
            steamProton = game.store === "steam" ? app.steamProton(k) : ({ choices: [], current: "" })
            optSteamProton.model = steamProton.choices
            optSteamProton.select(steamProton.current)
            optHud.select(opts.mangohud === undefined ? "default" : opts.mangohud)
            optPerf.select(opts.perf === undefined ? "default" : opts.perf)
            optPlatform.select(opts.platform === undefined ? "default" : opts.platform)
            optFps.select(opts.show_fps === undefined ? "default" : opts.show_fps)
            optScope.select(opts.gamescope === undefined ? "default" : opts.gamescope)
            optHdr.select(opts.gamescope_hdr === undefined ? "default" : opts.gamescope_hdr)
            resetArmed = false
            optMode.select(opts.gamemode === undefined ? "default" : opts.gamemode)
            optSaves.select(opts.cloud_saves === undefined ? "default" : opts.cloud_saves)
            optEnv.text = opts.env || ""
            optArgs.text = opts.args || ""
            optCover.text = opts.cover || ""
            open()
        }
        readonly property var triState: [{ label: qsTr("Use default"), value: "default" }, { label: qsTr("On"), value: true }, { label: qsTr("Off"), value: false }]
        property bool resetArmed: false

        contentItem: ColumnLayout {
            spacing: 14
            Text {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                color: theme.onSurfaceVariant
                font.pixelSize: 12
                visible: !gameOpts.compat && gameOpts.game.store !== "steam"
                text: qsTr("Battle.net games all run inside the Battle.net app, so Proton and overlay options are set on the Battle.net tile.")
            }
            // Steam games: Steam's own per-game compatibility tool, set from here.
            Row2 {
                visible: gameOpts.game.store === "steam"
                label: qsTr("Proton version (Steam's setting)")
                hint: gameOpts.steamProton.choices.length
                      ? "The same as the game's Properties → Compatibility in Steam. Cornerplay closes and reopens Steam to change it; Steam downloads a Valve Proton the first time a game uses it. Launch options stay in Steam."
                      : "Steam is not set up on this PC yet: start Steam and sign in once."
                KCombo {
                    id: optSteamProton
                    theme: win.theme; Layout.fillWidth: true
                    enabled: gameOpts.steamProton.choices.length > 0 && !app.steamShortcut.busy
                    onActivated: app.setSteamProton(gameOpts.key, currentValue)
                }
            }
            Row2 {
                visible: gameOpts.compat && !gameOpts.runsNative
                label: qsTr("Proton version")
                KCombo {
                    id: optProton
                    theme: win.theme; Layout.fillWidth: true
                    model: [{ label: qsTr("Use default"), value: "default" }].concat(app.protonVersions)
                    onActivated: app.setGameOption(gameOpts.key, "proton", currentValue)
                }
            }
            RowLayout {
                visible: gameOpts.compat
                spacing: 14
                Row2 {
                    label: qsTr("MangoHud")
                    KCombo { id: optHud; theme: win.theme; Layout.fillWidth: true; model: gameOpts.triState
                             onActivated: app.setGameOption(gameOpts.key, "mangohud", currentValue) }
                }
                Row2 {
                    label: qsTr("GameMode")
                    KCombo { id: optMode; theme: win.theme; Layout.fillWidth: true; model: gameOpts.triState
                             onActivated: app.setGameOption(gameOpts.key, "gamemode", currentValue) }
                }
            }
            // GOG games with a Linux version: which one to install.
            Row2 {
                visible: gameOpts.game.store === "gog" && !!gameOpts.game.linuxVersion
                label: qsTr("Version")
                hint: gameOpts.game.installed
                      ? "Installed: the " + (gameOpts.game.platform === "linux" ? "Linux" : "Windows") + " version. To switch, pick the other one, then uninstall and install again."
                      : "The Linux version runs without Proton (lighter, but old ones can need extra libraries); the Windows version runs through Proton."
                KCombo { id: optPlatform; theme: win.theme; Layout.fillWidth: true
                         model: [{ label: qsTr("Use default (Settings)"), value: "default" }, { label: qsTr("Linux version (native)"), value: "linux" },
                                 { label: qsTr("Windows version (Proton)"), value: "windows" }]
                         onActivated: app.setGameOption(gameOpts.key, "platform", currentValue) }
            }
            // Performance profile: frame cap + FSR upscaling (Steam games: set in Steam).
            RowLayout {
                visible: gameOpts.compat && gameOpts.game.store !== "battlenet"
                spacing: 14
                Row2 {
                    label: qsTr("Performance")
                    hint: qsTr("Battery saver caps at 30 fps, Balanced at 60, both with FSR upscaling when the game runs below your screen's resolution.")
                    KCombo { id: optPerf; theme: win.theme; Layout.fillWidth: true
                             model: [{ label: qsTr("Use default"), value: "default" }, { label: qsTr("No change"), value: "none" },
                                     { label: qsTr("Battery saver (30 fps)"), value: "battery" },
                                     { label: qsTr("Balanced (60 fps)"), value: "balanced" },
                                     { label: qsTr("Max quality (no cap)"), value: "quality" }]
                             onActivated: app.setGameOption(gameOpts.key, "perf", currentValue) }
                }
                Row2 {
                    label: qsTr("FPS counter")
                    KCombo { id: optFps; theme: win.theme; Layout.fillWidth: true; model: gameOpts.triState
                             onActivated: app.setGameOption(gameOpts.key, "show_fps", currentValue) }
                }
            }
            // Gamescope (not for the Battle.net app, which stays open after its games close).
            RowLayout {
                visible: gameOpts.compat && gameOpts.game.store !== "battlenet"
                spacing: 14
                Row2 {
                    label: qsTr("Gamescope")
                    hint: app.hasGamescope ? qsTr("Full screen at your screen's resolution, or drawn at 2/3 size and upscaled with FSR.")
                                           : "gamescope is not installed, so this has no effect yet."
                    KCombo { id: optScope; theme: win.theme; Layout.fillWidth: true
                             model: [{ label: qsTr("Use default"), value: "default" }, { label: qsTr("Off"), value: "off" },
                                     { label: qsTr("Full screen"), value: "fullscreen" }, { label: qsTr("FSR upscaling"), value: "fsr" }]
                             onActivated: app.setGameOption(gameOpts.key, "gamescope", currentValue) }
                }
                Row2 {
                    label: qsTr("HDR")
                    KCombo { id: optHdr; theme: win.theme; Layout.fillWidth: true; model: gameOpts.triState
                             onActivated: app.setGameOption(gameOpts.key, "gamescope_hdr", currentValue) }
                }
            }
            Row2 {
                visible: gameOpts.compat
                label: qsTr("Environment variables")
                KField { id: optEnv; theme: win.theme; Layout.fillWidth: true; placeholderText: qsTr("KEY=value KEY2=value")
                         onEditingFinished: app.setGameOption(gameOpts.key, "env", text) }
            }
            Row2 {
                visible: gameOpts.compat && gameOpts.game.store !== "battlenet"
                label: qsTr("Launch arguments")
                KField { id: optArgs; theme: win.theme; Layout.fillWidth: true; placeholderText: qsTr("-windowed -skipintro")
                         onEditingFinished: app.setGameOption(gameOpts.key, "args", text) }
            }
            RowLayout {
                visible: app.cloudSaveStores.includes(gameOpts.game.store)
                spacing: 14
                Row2 {
                    label: qsTr("Cloud saves")
                    KCombo { id: optSaves; theme: win.theme; Layout.fillWidth: true; model: gameOpts.triState
                             onActivated: app.setGameOption(gameOpts.key, "cloud_saves", currentValue) }
                }
                KButton {
                    theme: win.theme
                    Layout.alignment: Qt.AlignBottom
                    text: qsTr("Sync saves now")
                    enabled: !!gameOpts.game.installed
                    onClicked: app.syncNow(gameOpts.key)
                }
            }
            // When a game misbehaves.
            Row2 {
                visible: !!gameOpts.game.installed && gameOpts.game.store !== "steam"
                label: qsTr("Fix it")
                hint: gameOpts.resetArmed
                      ? "A fresh Proton prefix starts Windows settings from scratch. The old one is kept beside it (renamed), so saves stored there are not lost."
                      : "Repair checks every file and downloads the broken or missing ones."
                Flow {
                    Layout.fillWidth: true
                    spacing: 8
                    KButton { theme: win.theme; visible: ["epic", "gog", "amazon"].includes(gameOpts.game.store)
                              text: qsTr("Repair files"); iconName: "refresh-cw"
                              onClicked: { app.verifyGame(gameOpts.key); gameOpts.close() } }
                    KButton { theme: win.theme; visible: gameOpts.compat && !gameOpts.runsNative; danger: gameOpts.resetArmed
                              text: gameOpts.resetArmed ? qsTr("Really reset?") : qsTr("Reset Proton prefix"); iconName: "trash-2"
                              onClicked: { if (!gameOpts.resetArmed) { gameOpts.resetArmed = true; return }
                                           gameOpts.resetArmed = false; app.resetPrefix(gameOpts.key) } }
                    KButton { theme: win.theme; text: qsTr("Open log"); iconName: "folder-open"; onClicked: app.openLog(gameOpts.key) }
                }
            }
            Row2 {
                label: qsTr("Custom cover")
                hint: qsTr("An image file or a web address. Leave empty to use the automatic cover.")
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    KField { id: optCover; theme: win.theme; Layout.fillWidth: true; placeholderText: qsTr("Automatic")
                             onEditingFinished: app.setGameOption(gameOpts.key, "cover", text) }
                    KButton { theme: win.theme; text: qsTr("Choose…"); onClicked: coverPicker.open() }
                    KButton { theme: win.theme; text: qsTr("Reset"); enabled: optCover.text !== ""
                              onClicked: { optCover.text = ""; app.setGameOption(gameOpts.key, "cover", "") } }
                }
            }
        }
    }
    FileDialog {
        id: coverPicker
        title: qsTr("Choose a cover image")
        nameFilters: ["Images (*.png *.jpg *.jpeg *.webp)"]
        onAccepted: {
            app.setGameOption(gameOpts.key, "cover", selectedFile.toString())
            optCover.text = app.gameOptions(gameOpts.key).cover || ""
        }
    }

    // -------------------------------------------------------------------- splash
    // While the library loads: the icon's corner lights up and the name appears. Short, and it
    // goes as soon as there is something to show.
    //
    // It starts on the window's first frame: started while the window was still being built, it
    // was over before anything was on screen. Until the mark has come in, the library behind it
    // is not drawn at all (contentShown): the first frames then only have the splash to draw,
    // so they come at once and the main thread is free to start the animation on time. Its
    // animations are Animators (Qt's render thread), so a busy main thread cannot stutter them.
    property bool shown: false  // the window has drawn its first frame (TV mode's intro waits for it)
    readonly property bool contentShown: !splash.visible || splash.ready || win.tv
    Connections {
        target: win
        enabled: !win.shown
        function onFrameSwapped() { win.shown = true; splash.begin() }
    }
    Rectangle {
        id: splash
        objectName: "splash"
        anchors.fill: parent
        z: 1000
        color: theme.background
        // Started in TV mode with its intro on: the intro is the welcome, not this.
        visible: !(win.tv && app.settingsMap.tv_intro && !app.light)
        property bool started: false
        property bool ready: false
        property bool leaving: false
        readonly property bool loaded: app.totalCount > 0 || !app.refreshing
        function begin() {
            if (started || !visible) return
            started = true
            if (app.light) { readyTimer.interval = 300; return }
            splashIcon.play()
            splashIn.start()
        }
        function leave() {
            if (leaving) return
            leaving = true
            if (app.light) { visible = false; return }
            splashOut.start()
            goneTimer.start()
        }
        // Animators only move when the compositor asks for frames; a window it does not draw
        // (minimised, on another output) gets none. The splash never stays over the library
        // because of that: shortly after its fade should have ended, it goes regardless.
        Timer { id: goneTimer; interval: 700; onTriggered: splash.visible = false }
        // Ready once the mark has come in (its animation ends on the render thread and says so);
        // the timer only covers an animation that never reports back. Never longer than the cap.
        Connections {
            target: splashIcon
            function onPlayingChanged() { if (!splashIcon.playing && splash.started) splash.ready = true }
        }
        Timer { id: readyTimer; interval: 1500; running: splash.started; onTriggered: splash.ready = true }
        Timer { interval: 2600; running: splash.started; onTriggered: splash.leave() }
        // No frame at all (started minimised, a compositor that never shows the window): never
        // let a late first frame put the splash over a library that is long there.
        Timer { interval: 5000; running: true; onTriggered: if (!splash.started) { splash.started = true; splash.leave() } }
        onReadyChanged: { if (ready) app.startupAnimationDone(); if (ready && loaded) leave() }
        onLoadedChanged: if (ready && loaded) leave()
        SequentialAnimation {
            id: splashOut
            OpacityAnimator { target: splash; from: 1; to: 0; duration: 350; easing.type: Easing.InCubic }
            ScriptAction { script: splash.visible = false }
        }
        ParallelAnimation {
            id: splashIn
            ScaleAnimator { target: splashIcon; from: 0.85; to: 1.0; duration: 520; easing.type: Easing.OutBack }
            OpacityAnimator { target: splashIcon; from: 0; to: 1; duration: 360 }
            OpacityAnimator { target: splashName; from: 0; to: 1; duration: 600 }
        }
        Column {
            anchors.centerIn: parent
            spacing: 22
            BrandMark {
                id: splashIcon
                objectName: "splashIcon"
                anchors.horizontalCenter: parent.horizontalCenter
                size: 108
                opacity: app.light ? 1 : 0  // faded in by splashIn
            }
            WordMark {
                id: splashName
                anchors.horizontalCenter: parent.horizontalCenter
                showIcon: false; size: 30
                opacity: app.light ? 1 : 0
            }
        }
    }

    // -------------------------------------------------------------------- trailer on hover
    // Pointing at a cover for a moment plays its trailer inside it, muted (Settings > Appearance).
    property string trailerKey: ""
    property string trailerUrl: ""
    readonly property bool trailersOk: app.settingsMap.hover_trailers !== false && !app.light && !win.tv
                                       && typeof canPlayVideo !== "undefined" && canPlayVideo
                                       && Qt.application.state === Qt.ApplicationActive
    onHoverKeyChanged: { trailerKey = ""; trailerUrl = ""; if (hoverKey && trailersOk) trailerWait.restart(); else trailerWait.stop() }
    onTrailersOkChanged: if (!trailersOk) { trailerWait.stop(); trailerKey = ""; trailerUrl = "" }
    Timer {
        id: trailerWait
        interval: 1200
        onTriggered: {
            if (!win.hoverKey || grid.hoverIndex < 0 || win.popupOpen) return
            const d = app.gameDetails(win.hoverKey)   // {} until fetched; detailsReady follows
            if (d.trailer) { win.trailerKey = win.hoverKey; win.trailerUrl = d.trailer }
        }
    }
    Connections {
        target: app
        function onDetailsReady(key, d) {
            if (key === win.hoverKey && grid.hoverIndex >= 0 && !trailerWait.running && win.trailersOk && d.trailer) {
                win.trailerKey = key; win.trailerUrl = d.trailer
            }
        }
    }

    // -------------------------------------------------------------------- cover flight
    // Opening a game: its cover lifts off the grid and lands on the game page, where the page's
    // own cover takes over. Closing: it flies back into its place in the grid.
    Item {
        id: flyer
        parent: Overlay.overlay
        z: 1000
        visible: false
        property var covers: []
        property real fromRadius: 14
        property rect gridRect: Qt.rect(0, 0, 0, 0)
        property string key: ""
        readonly property bool on: !app.light && GraphicsInfo.api !== GraphicsInfo.Software
        // Where the game page shows its cover (it is the first thing on the page).
        function pageRect() {
            // (detail.x reads 0 until the page has opened: it always sits right of the sidebar)
            return Qt.rect(sidebar.width + detail.leftPadding, detail.topPadding - detailFlick.contentY, 220, 320)
        }
        function from(key, card) {
            if (!on || !card) return
            const r = card.mapToItem(null, 8, 8, card.width - 16, card.height - 16)
            gridRect = r; flyer.key = key
            covers = app.game(key).covers || []
            fromRadius = card.cornerRadius
            fly(r, pageRect(), true)
        }
        function back() {
            if (!on || !key || key !== win.selectedKey) return
            const card = grid.itemAtIndex(grid.currentIndex)
            if (!card || card.key !== key) return
            const r = card.mapToItem(null, 8, 8, card.width - 16, card.height - 16)
            if (r.y + r.height < 0 || r.y > win.height) return  // scrolled out of sight
            fly(pageRect(), r, false)
        }
        function fly(a, b, opening) {
            flight.stop()
            x = a.x; y = a.y; width = a.width; height = a.height
            ax.to = b.x; ay.to = b.y; aw.to = b.width; ah.to = b.height
            flight.opening = opening
            detailCoverBox.opacity = 0
            visible = true
            flight.start()
        }
        ParallelAnimation {
            id: flight
            property bool opening: true
            NumberAnimation { id: ax; target: flyer; property: "x"; duration: 380; easing.type: Easing.OutCubic }
            NumberAnimation { id: ay; target: flyer; property: "y"; duration: 380; easing.type: Easing.OutCubic }
            NumberAnimation { id: aw; target: flyer; property: "width"; duration: 380; easing.type: Easing.OutCubic }
            NumberAnimation { id: ah; target: flyer; property: "height"; duration: 380; easing.type: Easing.OutCubic }
            onFinished: { flyer.visible = false; detailCoverBox.opacity = 1; if (!flight.opening) flyer.key = "" }
        }
        RectangularShadow {
            anchors.fill: parent
            radius: 14; blur: 34; offset.y: 14
            color: Qt.alpha("black", 0.5)
        }
        RoundedArt {
            anchors.fill: parent
            radius: 14
            Rectangle { anchors.fill: parent; color: theme.surfaceContainerHigh }
            ArtImage { anchors.fill: parent; sources: flyer.covers; sourceSize.width: 400 }
        }
    }

    // -------------------------------------------------------------------- hover preview
    Item {
        id: preview
        property var g: ({})
        visible: false
        z: 50
        width: 260
        readonly property bool art: (g.heroes || []).length > 0
        height: pcol.implicitHeight + 26 + (art ? 78 : 0)
        opacity: visible ? 1 : 0
        scale: visible ? 1 : 0.96
        Behavior on opacity { NumberAnimation { duration: 140 } }
        Behavior on scale { enabled: !app.light; NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
        RectangularShadow {
            anchors.fill: parent
            visible: !app.light && GraphicsInfo.api !== GraphicsInfo.Software
            radius: 16; blur: 30; offset.y: 10
            color: Qt.alpha("black", 0.5)
        }
        RoundedArt {
            anchors.fill: parent
            radius: 16
            Rectangle { anchors.fill: parent; color: Qt.alpha(theme.surfaceContainerHigh, 0.97) }
            // The game's wide art along the top, fading into the card.
            ArtImage {
                id: previewArt
                visible: preview.art
                width: parent.width; height: 104
                sources: preview.visible ? (preview.g.heroes || []) : []
                sourceSize.width: 520
                opacity: status === Image.Ready ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: 200 } }
            }
            Rectangle {
                visible: preview.art
                width: parent.width; height: 104
                gradient: Gradient {
                    GradientStop { position: 0.35; color: "transparent" }
                    GradientStop { position: 1.0; color: Qt.alpha(theme.surfaceContainerHigh, 0.97) }
                }
            }
        }
        Rectangle {
            anchors.fill: parent; radius: 16; color: "transparent"
            border.width: 1; border.color: theme.dark === false ? Qt.alpha("black", 0.08) : Qt.alpha("white", 0.09)
        }
        Column {
            id: pcol
            x: 16; y: preview.art ? 90 : 14
            width: parent.width - 32
            spacing: 6
            Text { width: parent.width; text: preview.g.title || ""; color: theme.onSurface; font.pixelSize: 15; font.weight: Font.Bold; wrapMode: Text.WordWrap }
            Row { spacing: 6
                  StoreTile { anchors.verticalCenter: parent.verticalCenter; size: 16; store: preview.g.store || "" }
                  Text { text: (preview.g.storeName || "") + (preview.g.installed ? qsTr("  ·  installed") : qsTr("  ·  not installed")); color: theme.onSurfaceVariant; font.pixelSize: 12 } }
            Text { width: parent.width; visible: text !== ""; text: preview.g.key ? app.playedText(preview.g.playtime, preview.g.lastPlayed) : ""
                   color: theme.onSurfaceVariant; font.pixelSize: 12; wrapMode: Text.WordWrap }
            Text { visible: !!preview.g.status || !!preview.g.rating; color: theme.onSurfaceVariant; font.pixelSize: 12
                   text: [({ playing: qsTr("Playing"), want: qsTr("Want to play"), finished: qsTr("Finished"), dropped: qsTr("Dropped") })[preview.g.status] || "",
                          preview.g.rating ? "\u2605".repeat(preview.g.rating) : ""].filter(x => x).join("   ") }
            Text { visible: !!preview.g.protondb; color: theme.onSurfaceVariant; font.pixelSize: 12
                   text: qsTr("ProtonDB: ") + (preview.g.protondb || "").charAt(0).toUpperCase() + (preview.g.protondb || "").slice(1) }
        }
    }

    // -------------------------------------------------------------------- built-in sign-in window
    Loader {
        id: loginWindow
        active: false
        source: typeof webLogin !== "undefined" && webLogin ? "LoginWindow.qml" : ""
        Connections {
            target: loginWindow.item
            function onFallback() { app.loginBegin(loginWindow.item.store, true) }
        }
    }

    // Blizzard account: its own sign-in window and the hidden page that reads the owned games.
    // Loaded only once an account is linked (or being linked): it starts Chromium.
    Loader {
        id: blizzardSync
        active: false  // switched on by the first sync or sign-in (it starts Chromium)
        source: "BlizzardSync.qml"
    }
    // Loaded by file name only when needed: naming LoginWindow here would load Chromium at every start.
    Loader { id: blizzardLogin }

    // -------------------------------------------------------------------- screenshot viewer
    Popup {
        id: viewer
        objectName: "viewer"
        property var shots: []
        property int at: 0
        function show(list, i) { shots = list || []; at = i; open() }
        function step(d) { if (shots.length) at = (at + d + shots.length) % shots.length }
        parent: Overlay.overlay
        x: 0; y: 0
        width: win.width; height: win.height
        modal: true
        focus: true
        padding: 0
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle { color: Qt.alpha("black", 0.92) }
        enter: Transition { enabled: !app.light; NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 180 } }
        exit: Transition { enabled: !app.light; NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 120 } }
        contentItem: Item {
            focus: true
            Keys.onLeftPressed: viewer.step(-1)
            Keys.onRightPressed: viewer.step(1)
            readonly property var shot: viewer.shots.length ? viewer.shots[viewer.at] : ({})
            Image {  // the small version shows at once; the full one replaces it when it arrives
                anchors.fill: parent; anchors.margins: 70
                source: parent.shot.thumb || ""
                fillMode: Image.PreserveAspectFit
                visible: full.status !== Image.Ready
            }
            Image {
                id: full
                anchors.fill: parent; anchors.margins: 70
                source: parent.shot.full || ""
                fillMode: Image.PreserveAspectFit
                asynchronous: true
            }
            Round { anchors.left: parent.left; anchors.leftMargin: 14; anchors.verticalCenter: parent.verticalCenter; icon: "play"; rotation: 180; visible: viewer.shots.length > 1; onTapped: viewer.step(-1) }
            Round { anchors.right: parent.right; anchors.rightMargin: 14; anchors.verticalCenter: parent.verticalCenter; icon: "play"; visible: viewer.shots.length > 1; onTapped: viewer.step(1) }
            Round { anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 14; icon: "x"; onTapped: viewer.close() }
            Text {
                anchors { horizontalCenter: parent.horizontalCenter; bottom: parent.bottom; bottomMargin: 26 }
                text: (viewer.at + 1) + " / " + viewer.shots.length
                color: Qt.alpha("white", 0.8)
                font.pixelSize: 14
            }
        }
    }

    // -------------------------------------------------------------------- toasts
    ListModel { id: toasts }
    Column {
        z: 1000
        parent: Overlay.overlay
        anchors { bottom: parent.bottom; horizontalCenter: parent.horizontalCenter; bottomMargin: 24 }
        spacing: 8
        Repeater {
            model: toasts
            Rectangle {
                id: toast
                required property string message
                required property int index
                anchors.horizontalCenter: parent.horizontalCenter
                width: Math.min(toastText.implicitWidth + 70, win.width - 80)
                height: Math.max(48, toastText.height + 26)
                radius: Math.min(24, height / 2)
                color: Qt.alpha(theme.surfaceContainerHighest, 0.96)
                border.width: 1
                border.color: theme.dark === false ? Qt.alpha("black", 0.08) : Qt.alpha("white", 0.1)
                RectangularShadow {
                    z: -1
                    anchors.fill: parent
                    visible: !app.light && GraphicsInfo.api !== GraphicsInfo.Software
                    radius: parent.radius; blur: 26; offset.y: 8
                    color: Qt.alpha("black", 0.45)
                }
                // How long it stays: a thin line in the accent that runs out.
                Rectangle {
                    anchors { bottom: parent.bottom; bottomMargin: 5; horizontalCenter: parent.horizontalCenter }
                    height: 2; radius: 1
                    width: (parent.width - 2 * parent.radius) * toast.life
                    color: Qt.alpha(toast.bad ? theme.error : theme.primary, 0.7)
                }
                property real life: 1
                NumberAnimation on life { from: 1; to: 0; duration: 5000; running: !app.light }
                // Slide up and fade in.
                opacity: 0
                transform: Translate { id: toastShift; y: 14 }
                Component.onCompleted: toastIn.start()
                ParallelAnimation {
                    id: toastIn
                    NumberAnimation { target: toast; property: "opacity"; to: 1; duration: app.light ? 0 : 200; easing.type: Easing.OutCubic }
                    NumberAnimation { target: toastShift; property: "y"; to: 0; duration: app.light ? 0 : 260; easing.type: Easing.OutCubic }
                }
                // An icon picked from what the message says.
                readonly property bool bad: /fail|could not|not (uploaded|synced|added|found|started)|rejected|error/i.test(message)
                readonly property string icon: bad ? "x"
                    : /^launching/i.test(message) ? "play"
                    : /update available|updates available/i.test(message) ? "arrow-up"
                    : /^removed|uninstall/i.test(message) ? "trash-2"
                    : /save|sync|upload|cloud/i.test(message) ? "cloud"
                    : /hidden/i.test(message) ? "eye-off"
                    : /cancel/i.test(message) ? "x"
                    : /installed|updated|added|is back|copied|in steam|ready/i.test(message) ? "check"
                    : "gamepad-2"
                Rectangle {
                    x: 12; anchors.verticalCenter: parent.verticalCenter
                    width: 28; height: 28; radius: 14
                    color: Qt.alpha(toast.bad ? theme.error : theme.primary, 0.18)
                    Icon { anchors.centerIn: parent; name: toast.icon; size: 15; color: toast.bad ? theme.error : theme.primary }
                }
                Text {
                    id: toastText
                    x: 50; anchors.verticalCenter: parent.verticalCenter
                    width: Math.min(implicitWidth, win.width - 144)
                    wrapMode: Text.WordWrap
                    maximumLineCount: 3
                    elide: Text.ElideRight
                    text: toast.message
                    color: theme.onSurface
                    font.pixelSize: 13
                }
                Timer { interval: 5000; running: true; onTriggered: toasts.remove(0) }
                MouseArea {  // takes the click, so a card under the message does not open
                    anchors.fill: parent
                    onClicked: toasts.remove(toast.index)
                }
            }
        }
    }
}
