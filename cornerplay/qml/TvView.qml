import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Effects
import QtQuick.Layouts
import "protondb.js" as ProtonDB

// Full-screen, couch-distance view driven entirely by arrows / a controller.
FocusScope {
    id: tv
    required property var theme
    signal exit()

    property var cur: ({})

    // The focused game's own colour (from its cover) tints the glow and the active tab.
    property string gameAccent: ""
    property color accent: gameAccent || theme.primary
    Behavior on accent { enabled: !app.light; ColorAnimation { duration: 450 } }
    readonly property var tint: {
        const c = tv.accent
        const lum = 0.299 * c.r + 0.587 * c.g + 0.114 * c.b
        return Object.assign({}, tv.theme, { primary: c.toString(), onPrimary: lum > 0.55 ? "#1b1b1f" : "#ffffff" })
    }
    // Description and genres, asked for once the focus rests (no store requests while scrolling past).
    property var info: ({})
    property string infoKey: ""
    // The trailer starts after the focus has rested a moment (and stops as soon as it moves).
    property string trailerUrl: ""
    Timer { id: trailerTimer; interval: 2500; onTriggered: tv.trailerUrl = tv.info.trailer || "" }
    onInfoChanged: { trailerUrl = ""; if (info.trailer) trailerTimer.restart(); else trailerTimer.stop() }
    property var ach: ({})
    property var anim: ({})   // animated cover / banner (SteamGridDB)
    Timer { id: infoTimer; interval: 350; onTriggered: {
        tv.info = tv.infoKey ? app.gameDetails(tv.infoKey) : ({})
        tv.ach = tv.infoKey ? app.achievements(tv.infoKey) : ({})
        tv.anim = tv.infoKey ? app.animatedArt(tv.infoKey) : ({})
    } }
    // Animated art plays only when it costs nothing that matters: plugged in (or a desktop),
    // full effects, someone is using the screen, and Cornerplay is in front.
    readonly property bool plugged: topStatus.batt.level === undefined || !!topStatus.batt.charging
    readonly property bool animOk: !!app.settingsMap.tv_animated && !app.light && !tv.calm && tv.plugged
                                   && tv.visible && Qt.application.state === Qt.ApplicationActive
    onCurChanged: {
        if ((cur.key || "") === infoKey) return  // same game, just refreshed
        infoKey = cur.key || ""
        gameAccent = cur.key ? app.gameColour(cur.key) : ""
        info = ({}); ach = ({}); anim = ({})
        infoTimer.restart()
    }
    readonly property var storeIds: [""].concat(app.storesInfo.filter(s => s.id !== "custom" || s.count > 0).map(s => s.id))

    // Shelves: Continue playing, Favourites, collections, Recently added, Library. Up / down.
    property var shelfList: []
    property int shelfAt: 0
    readonly property var shelf: shelfList[shelfAt] || ({ id: "", name: "Library" })
    property bool shelvesShown: false   // the first time, start on the top shelf, like a console's home
    function loadShelves() {
        const keep = tvLibrary.shelf
        shelfList = app.shelfList()
        const i = shelfList.findIndex(s => s.id === keep)
        shelfAt = !shelvesShown ? 0 : i >= 0 ? i : shelfList.length - 1
        shelvesShown = true
        if (!searching && tvLibrary.search === "") tvLibrary.shelf = shelf.id
    }
    readonly property var nextShelf: tvLibrary.search === "" ? (shelfList[shelfAt + 1] || null) : null
    onNextShelfChanged: tvNextLibrary.shelf = nextShelf ? nextShelf.id : ""
    Connections {
        target: tvLibrary
        function onFilterChanged() {
            tvNextLibrary.storeFilter = tvLibrary.storeFilter
            tvNextLibrary.installedOnly = tvLibrary.installedOnly
        }
    }
    function stepShelf(step) {
        if (tvLibrary.search !== "") return
        const i = Math.max(0, Math.min(shelfList.length - 1, shelfAt + step))
        if (i === shelfAt) return
        app.uiSound("move")
        shelfAt = i
        tvLibrary.shelf = shelf.id
        grid.currentIndex = 0
        grid.contentX = 0
        sync()
    }
    Connections {
        target: app
        function onCollectionsChanged() { tv.loadShelves() }
        function onStoresChanged() { if (tv.visible) Qt.callLater(tv.loadShelves) }
    }

    // Search: an on-screen keyboard for the controller; a real keyboard just types.
    property bool searching: false
    function openSearch(first) {
        if (!searching) { searching = true; tvLibrary.shelf = "" }
        if (first) tvLibrary.search = tvLibrary.search + first
        keys.forceActiveFocus()
        grid.currentIndex = 0; sync()
    }
    function closeSearch(keepResults) {
        searching = false
        if (!keepResults || tvLibrary.search === "") clearSearch()
        grid.forceActiveFocus(); sync()
    }
    function clearSearch() {
        tvLibrary.search = ""
        tvLibrary.shelf = shelf.id
        grid.currentIndex = 0; sync()
    }

    function sync() { cur = app.game(tvLibrary.keyAt(grid.currentIndex)); wake() }

    // Calm: after 30 s without input the moving art and the trailer stop (they redraw the
    // whole screen 60 times a second: a drained Steam Deck battery while you look at a menu).
    property bool calm: false
    function wake() { calm = false; calmTimer.restart() }
    Timer { id: calmTimer; interval: 30000; running: tv.visible; onTriggered: tv.calm = true }
    function cycleStore(step) {
        app.uiSound("move")
        const i = storeIds.indexOf(tvLibrary.storeFilter)
        tvLibrary.storeFilter = storeIds[(i + step + storeIds.length) % storeIds.length]
        grid.currentIndex = 0
        sync()
    }
    function accept() {
        if (!cur.key) return
        app.uiSound("select")
        const target = app.launchTarget(cur.key)
        if (target) app.play(target)
        else panel.show()
    }
    function buildActions() {
        const out = []
        if (!cur.key) return out
        const copies = cur.copies.length ? cur.copies : [{ key: cur.key, storeName: cur.storeName }]
        const removable = []
        for (const c of copies) {
            const g = app.game(c.key)
            if (g.job) out.push({ label: "Cancel " + ({ install: "install", update: "update" }[g.job] || "removal") + " · " + c.storeName, act: "cancel", key: c.key })
            else if (g.installed) {
                out.push({ label: "Play on " + c.storeName, act: "play", key: c.key })
                if (g.update) out.push({ label: "Update on " + c.storeName, act: "update", key: c.key })
                if (g.store !== "battlenet") removable.push(c)
            }
            else out.push({ label: "Install from " + c.storeName, act: "install", key: c.key })
        }
        for (const c of removable) out.push({ label: "Uninstall from " + c.storeName, act: "uninstall", key: c.key })
        if (app.nowPlaying.some(p => p.key === cur.key)) {
            out.unshift({ label: "Force close (if it hangs)", act: "kill", key: cur.key })
            out.unshift({ label: "Quit game", act: "quit", key: cur.key })
        }
        out.push({ label: cur.favourite ? "Remove from favourites" : "Add to favourites", act: "fav", key: cur.key })
        // Backlog status: one row that steps through the choices.
        const names = { "": "None", playing: "Playing", want: "Want to play", finished: "Finished", dropped: "Dropped" }
        out.push({ label: "Status: " + names[cur.status || ""] + "  \u25B8", act: "status", key: cur.key })
        out.push({ label: cur.hidden ? "Unhide game" : "Hide game", act: cur.hidden ? "unhide" : "hide", key: cur.key })
        out.push({ label: "Close", act: "close", key: "" })
        return out
    }

    function grab() { loadShelves(); grid.forceActiveFocus(); sync() }
    onVisibleChanged: if (visible) { grab(); maybeIntro() }
    Component.onCompleted: if (visible) { Qt.callLater(grab); Qt.callLater(maybeIntro) }
    Connections {
        target: app
        function onGameChanged(key) { tv.sync(); if (panel.visible) panel.rows = tv.buildActions() }
        function onGameColourReady(key, colour) { if (key === tv.cur.key) tv.gameAccent = colour }
        function onDetailsReady(key, d) { if (key === tv.infoKey) tv.info = d }
        function onAchievementsReady(key, d) { if (key === tv.infoKey) tv.ach = d }
        function onAnimatedArtReady(key, d) { if (key === tv.infoKey) tv.anim = d }
    }

    // One of the two full-screen art images that take turns (see stage).
    component ArtLayer: ArtImage {
        property string tag: ""
        anchors.fill: parent
        sourceSize.width: Math.min(app.light ? 1280 : 1920, Math.max(640, Math.ceil(width * Screen.devicePixelRatio / 40) * 40))
        horizontalAlignment: Image.AlignRight
        Behavior on opacity { enabled: !app.light; NumberAnimation { duration: 450; easing.type: Easing.InOutQuad } }
        // Slow pan and zoom while the art is showing (off in Light mode).
        transformOrigin: Item.Right
        transform: Translate { id: drift }
        readonly property bool drifting: opacity > 0 && status === Image.Ready && !app.light && tv.visible
                                         && !tv.calm && Qt.application.state === Qt.ApplicationActive
        SequentialAnimation on scale {
            running: drifting
            loops: Animation.Infinite
            NumberAnimation { from: 1.0; to: 1.08; duration: 18000; easing.type: Easing.InOutSine }
            NumberAnimation { from: 1.08; to: 1.0; duration: 18000; easing.type: Easing.InOutSine }
        }
        SequentialAnimation {
            running: drifting
            loops: Animation.Infinite
            NumberAnimation { target: drift; property: "x"; from: 0; to: -40; duration: 18000; easing.type: Easing.InOutSine }
            NumberAnimation { target: drift; property: "x"; from: -40; to: 0; duration: 18000; easing.type: Easing.InOutSine }
        }
        onStatusChanged: {
            if (stage.incoming !== tag) return
            if (status === Image.Ready) {
                stage.showA = tag === "a"; stage.none = false; stage.incoming = ""
            } else if (status === Image.Error && at >= sources.length - 1) {
                stage.none = true; stage.incoming = ""
            }
        }
    }

    Rectangle { anchors.fill: parent; color: theme.background }

    // ---------------------------------------------------------------- full-screen artwork
    // The focused game's wide art fills the screen and cross-fades to the next game's.
    // Two images take turns: the incoming one loads hidden, then fades in over the other.
    Item {
        id: stage
        anchors.fill: parent
        visible: tv.visible
        property bool showA: true
        property bool none: true      // no wide art for this game: show its blurred cover instead
        property string incoming: ""  // "a" or "b" while that image loads the next game's art
        function load(list) {
            if (!list || !list.length) { none = true; incoming = ""; return }
            const next = showA ? artB : artA
            incoming = next.tag
            next.sources = list
            if (next.status === Image.Ready && next.at === 0) { showA = next.tag === "a"; none = false; incoming = "" }
        }
        // Wait until the focus settles, so fast scrolling does not load every game on the way.
        Timer { id: settle; interval: 140; onTriggered: stage.load(tv.cur.heroes) }
        Connections {
            target: tv
            function onCurChanged() {
                if (JSON.stringify(tv.cur.heroes || []) !== stage.lastSig) {
                    stage.lastSig = JSON.stringify(tv.cur.heroes || [])
                    settle.restart()
                }
            }
        }
        property string lastSig: ""

        ArtLayer { id: artA; tag: "a"; opacity: !stage.none && stage.showA ? 1 : 0 }
        ArtLayer { id: artB; tag: "b"; opacity: !stage.none && !stage.showA ? 1 : 0 }
        AnimatedImage {
            id: animHero
            objectName: "tvAnimHero"
            anchors.fill: parent
            source: tv.animOk && tv.anim.hero ? tv.anim.hero : ""
            asynchronous: true
            // Keep Qt's default cache: an AnimatedImage from the web with cache: false crashes Qt 6.12.
            fillMode: Image.PreserveAspectCrop
            horizontalAlignment: Image.AlignRight
            playing: tv.animOk
            opacity: status === Image.Ready ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: 450 } }
        }
        Loader {
            anchors.fill: parent
            active: typeof canPlayVideo !== "undefined" && canPlayVideo && app.settingsMap.tv_trailers
                    && !app.light && tv.visible && tv.trailerUrl !== ""
                    && Qt.application.state === Qt.ApplicationActive  // never behind a running game
                    && !tv.calm
            source: "TvTrailer.qml"
            onLoaded: item.source = Qt.binding(() => tv.trailerUrl)
        }

        Image {
            id: backdrop
            anchors.fill: parent
            source: stage.none && !app.light ? (tv.cur.cover || "") : ""
            asynchronous: true
            fillMode: Image.PreserveAspectCrop
            sourceSize.width: 200
            visible: false
        }
        MultiEffect {
            anchors.fill: parent
            source: backdrop
            visible: stage.none && !app.light && GraphicsInfo.api !== GraphicsInfo.Software && backdrop.status === Image.Ready
            blurEnabled: true
            blur: 1.0
            blurMax: 64
            opacity: 0.45
        }

        // No wide art: the cover itself stands large on the right, lit in the game's colour,
        // so the screen is never an empty band.
        Rectangle {
            anchors.fill: parent
            opacity: stage.none ? 1 : 0
            Behavior on opacity { enabled: !app.light; NumberAnimation { duration: 450 } }
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.3; color: "transparent" }
                GradientStop { position: 1.0; color: Qt.alpha(tv.accent, 0.30) }
            }
        }
        ArtImage {
            id: poster
            // From below the tabs to just above the cover row.
            readonly property real h: Math.round(Math.max(180, tv.height - grid.height - tv.height * 0.12 - 150))
            anchors { right: parent.right; rightMargin: Math.round(tv.width * 0.07); top: parent.top; topMargin: Math.round(tv.height * 0.12) }
            height: h
            width: Math.round(h / 1.5)
            sources: stage.none && tv.cur.key ? (tv.cur.covers || [tv.cur.cover]).filter(u => !!u) : []
            sourceSize.width: 600
            fillMode: Image.PreserveAspectCrop
            opacity: stage.none && status === Image.Ready ? 1 : 0
            Behavior on opacity { enabled: !app.light; NumberAnimation { duration: 450; easing.type: Easing.InOutQuad } }
            transform: Rotation { origin.x: poster.width; origin.y: poster.height / 2; axis { x: 0; y: 1; z: 0 } angle: -9 }
            layer.enabled: !app.light && GraphicsInfo.api !== GraphicsInfo.Software
            layer.effect: MultiEffect {
                shadowEnabled: true
                shadowColor: tv.accent
                shadowBlur: 1.0
                shadowOpacity: 0.55
                shadowScale: 1.04
            }
        }

        // Shade: dark on the left for the title, and at the bottom for the covers.
        Rectangle {
            anchors.fill: parent
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: Qt.alpha(theme.background, 0.94) }
                GradientStop { position: 0.3; color: Qt.alpha(theme.background, 0.72) }
                GradientStop { position: 0.55; color: Qt.alpha(theme.background, 0.25) }
                GradientStop { position: 0.75; color: Qt.alpha(theme.background, 0.0) }
            }
        }
        Rectangle {
            anchors.fill: parent
            gradient: Gradient {
                GradientStop { position: 0.0; color: Qt.alpha(theme.background, 0.55) }
                GradientStop { position: 0.16; color: Qt.alpha(theme.background, 0.0) }
                GradientStop { position: 0.5; color: Qt.alpha(theme.background, 0.0) }
                GradientStop { position: 0.82; color: Qt.alpha(theme.background, 0.85) }
                GradientStop { position: 1.0; color: theme.background }
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 48
        anchors.bottomMargin: 28
        spacing: 18

        // Store tabs. On narrower screens (the Steam Deck) the stores you are not on show only
        // their logo, and the row never pushes the layout wider than the screen.
        RowLayout {
            readonly property bool compact: tv.width < 1500
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            clip: true
            spacing: 12
            WordMark { size: 30; Layout.rightMargin: 20 }
            Repeater {
                model: tv.storeIds
                Rectangle {
                    required property string modelData
                    readonly property bool active: tvLibrary.storeFilter === modelData
                    readonly property var info: app.storesInfo.find(s => s.id === modelData) || ({ name: "All games", color: "" })
                    implicitWidth: tabRow.implicitWidth + 36
                    implicitHeight: 46
                    radius: 23
                    color: active ? tv.tint.primary : tabHover.hovered ? Qt.alpha(theme.onSurface, 0.1) : Qt.alpha(theme.background, 0.35)
                    HoverHandler { id: tabHover; cursorShape: Qt.PointingHandCursor }
                    border.width: 0
                    border.color: theme.outlineVariant
                    Row {
                        id: tabRow
                        anchors.centerIn: parent
                        spacing: 9
                        StoreTile {
                            visible: parent.parent.modelData !== ""
                            anchors.verticalCenter: parent.verticalCenter
                            size: 26
                            store: parent.parent.modelData
                        }
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            visible: !parent.parent.parent.compact || parent.parent.active || parent.parent.modelData === ""
                            text: parent.parent.info.name
                            color: parent.parent.active ? tv.tint.onPrimary : theme.onSurfaceVariant
                            font.pixelSize: 18
                            font.weight: parent.parent.active ? Font.DemiBold : Font.Normal
                        }
                    }
                    TapHandler { onTapped: { tvLibrary.storeFilter = parent.modelData; grid.currentIndex = 0; tv.sync() } }
                }
            }
            Item { Layout.fillWidth: true }
            // Console-style status: battery (Steam Deck, laptops) and the time.
            Row {
                id: topStatus
                spacing: 18
                property var batt: ({})
                property string clock: ""
                function tick() {
                    clock = Qt.formatTime(new Date(), Qt.locale().timeFormat(Locale.ShortFormat))
                    batt = app.battery()
                }
                Timer { interval: 20000; running: tv.visible; repeat: true; triggeredOnStart: true; onTriggered: topStatus.tick() }
                Row {
                    visible: topStatus.batt.level !== undefined
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 6
                    Icon {
                        anchors.verticalCenter: parent.verticalCenter
                        name: topStatus.batt.charging ? "battery-charging" : "battery"
                        size: 24
                        color: (topStatus.batt.level || 100) <= 15 && !topStatus.batt.charging ? theme.error : theme.onSurfaceVariant
                    }
                    Text { anchors.verticalCenter: parent.verticalCenter; text: (topStatus.batt.level || 0) + "%"; color: theme.onSurfaceVariant; font.pixelSize: 18 }
                }
                Rectangle {
                    visible: app.nowPlaying.length > 0
                    anchors.verticalCenter: parent.verticalCenter
                    height: 36; radius: 18
                    width: playingText.implicitWidth + 44
                    color: Qt.alpha(tv.tint.primary, 0.2)
                    border.width: 1; border.color: tv.tint.primary
                    Icon { x: 14; anchors.verticalCenter: parent.verticalCenter; name: "play"; size: 14; color: tv.tint.primary }
                    Text { id: playingText; x: 34; anchors.verticalCenter: parent.verticalCenter
                           text: app.nowPlaying.length ? app.nowPlaying[0].title : ""; color: theme.onSurface; font.pixelSize: 16 }
                }
                Row {  // who is playing: initial in a circle (and the name when there are several people)
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 10
                    Rectangle {
                        width: 38; height: 38; radius: 19
                        color: tv.tint.primary
                        Text { anchors.centerIn: parent; text: (app.profile || "?").charAt(0).toUpperCase(); color: tv.tint.onPrimary
                               font.pixelSize: 18; font.weight: Font.Bold }
                    }
                    Text { visible: app.profiles.length > 1; anchors.verticalCenter: parent.verticalCenter
                           text: app.profile; color: theme.onSurfaceVariant; font.pixelSize: 18 }
                }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: topStatus.clock
                    color: theme.onSurface
                    font.pixelSize: 24
                    font.weight: Font.Medium
                }
            }
        }

        // The focused game, big, over its artwork. On short screens (the Steam Deck) the
        // description and then the genres step aside so the title never runs into the tabs.
        Item {
            id: infoArea
            Layout.fillWidth: true
            Layout.fillHeight: true
            readonly property real core: titleBlock.height + metaRow.height + playedLine.height + actionsRow.height + 60
            readonly property bool roomForGenres: height >= core + 40
            readonly property bool roomForText: height >= core + 40 + 110
            ColumnLayout {
                anchors { left: parent.left; bottom: parent.bottom; bottomMargin: 6 }
                width: Math.min(parent.width * 0.62, 980)
                spacing: 12
                LogoTitle {
                    id: titleBlock
                    Layout.fillWidth: true
                    logos: tv.cur.logos || []
                    title: tv.cur.title || ""
                    color: theme.onSurface
                    pixelSize: Math.round(Math.min(72, Math.max(40, tv.height * 0.06)))
                    logoHeight: Math.round(Math.min(170, Math.max(80, Math.min(tv.height * 0.15, infoArea.height * 0.3))))
                    maxWidth: Math.min(width, 640)
                }
                Row {
                    id: metaRow
                    spacing: 14
                    Repeater {
                        model: tv.cur.key ? (tv.cur.copies.length ? tv.cur.copies : [{ key: tv.cur.key, storeColor: tv.cur.storeColor }]) : []
                        StoreIcon {
                            required property var modelData
                            anchors.verticalCenter: parent.verticalCenter
                            size: 24
                            store: modelData.key.split(":")[0]
                            color: modelData.storeColor || "white"
                        }
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        color: theme.onSurface
                        opacity: 0.85
                        font.pixelSize: 19
                        text: {
                            if (!tv.cur.key) return ""
                            const stores = tv.cur.copies.length ? tv.cur.copies.map(c => c.storeName).join(", ") : tv.cur.storeName
                            const pct = Math.max(0, Math.floor(tv.cur.progress)) + "%"
                            const state = tv.cur.job === "install" ? "Installing " + pct
                                        : tv.cur.job === "update" ? "Updating " + pct
                                        : tv.cur.job === "dlc" ? "Installing DLC " + pct
                                        : tv.cur.job === "move" ? "Moving " + pct
                                        : tv.cur.job ? "Removing…"
                                        : tv.cur.installed ? (tv.cur.update ? "Update available" : "Installed") : "Not installed"
                            return stores + "  ·  " + state
                        }
                    }
                    Rectangle {  // ProtonDB rating
                        visible: !!tv.cur.protondb
                        anchors.verticalCenter: parent.verticalCenter
                        height: 30; radius: 15
                        width: tvPdb.implicitWidth + 40
                        color: Qt.alpha(theme.background, 0.5)
                        border.width: 1
                        border.color: ProtonDB.color(tv.cur.protondb || "")
                        StoreIcon { x: 11; anchors.verticalCenter: parent.verticalCenter; size: 16; store: "protondb"; color: ProtonDB.color(tv.cur.protondb || "") }
                        Text { id: tvPdb; x: 33; anchors.verticalCenter: parent.verticalCenter; text: "ProtonDB " + ProtonDB.label(tv.cur.protondb || ""); color: theme.onSurface; font.pixelSize: 14; font.weight: Font.DemiBold }
                    }
                }
                Text {
                    id: playedLine
                    readonly property string played: tv.cur.key ? app.playedText(tv.cur.playtime, tv.cur.lastPlayed) : ""
                    readonly property string trophies: tv.ach.total ? "\u{1F3C6} " + tv.ach.done + " / " + tv.ach.total : ""
                    visible: text !== ""
                    readonly property string pad: tv.info.controller === "partial" ? "\u{1F3AE} Partial controller support"
                                                  : tv.info.controller === "" && !!tv.cur.steamAppId ? "\u2328 Mouse and keyboard" : ""
                    readonly property string stars: tv.cur.rating ? "\u2605".repeat(tv.cur.rating) + "\u2606".repeat(5 - tv.cur.rating) : ""
                    text: [played, trophies, stars, pad].filter(t => !!t).join("   \u00B7   ")
                    color: theme.onSurfaceVariant
                    font.pixelSize: 17
                }
                Row {
                    spacing: 8
                    visible: (tv.info.genres || []).length > 0 && infoArea.roomForGenres
                    Repeater {
                        model: tv.info.genres || []
                        Rectangle {
                            required property string modelData
                            height: 28; radius: 14
                            width: tvGenre.implicitWidth + 24
                            color: Qt.alpha(theme.background, 0.45)
                            border.width: 1
                            border.color: tv.tint.primary
                            Text { id: tvGenre; anchors.centerIn: parent; text: modelData; color: theme.onSurface; font.pixelSize: 13; font.weight: Font.DemiBold }
                        }
                    }
                }
                Text {
                    Layout.fillWidth: true
                    Layout.maximumWidth: Math.min(680, tv.width * 0.42)
                    visible: text !== "" && infoArea.roomForText
                    text: tv.info.description || ""
                    style: Text.Raised; styleColor: Qt.alpha("black", 0.55)  // stays readable over bright art
                    color: theme.onSurface
                    opacity: 0.82
                    font.pixelSize: 16
                    lineHeight: 1.25
                    wrapMode: Text.WordWrap
                    maximumLineCount: 3
                    elide: Text.ElideRight
                }
                // The two things you can do, with the button that does them.
                Row {
                    id: actionsRow
                    Layout.topMargin: 6
                    spacing: 14
                    visible: !!tv.cur.key
                    Rectangle {
                        id: playBtn
                        readonly property string label: tv.cur.job ? ({ install: "Installing", update: "Updating", dlc: "Installing DLC", move: "Moving", verify: "Checking files", fix: "Fixing", queued: "Queued" }[tv.cur.job] || "Removing")
                                                                       + (tv.cur.job !== "uninstall" ? " " + Math.max(0, Math.floor(tv.cur.progress || 0)) + "%" : "")
                                                        : tv.cur.installed ? (tv.cur.playtime ? "Resume" : "Play") : "Install"
                        height: 56; radius: 28
                        width: playRow.implicitWidth + 44
                        color: tv.tint.primary
                        Rectangle {  // install progress fills the button
                            visible: !!tv.cur.job
                            anchors { left: parent.left; top: parent.top; bottom: parent.bottom }
                            width: parent.width * Math.max(0, Math.min(1, (tv.cur.progress || 0) / 100))
                            radius: parent.radius
                            color: Qt.alpha(tv.tint.onPrimary, 0.18)
                        }
                        Row {
                            id: playRow
                            anchors.centerIn: parent
                            spacing: 10
                            PadButton { visible: pad.connected || pad.deck; anchors.verticalCenter: parent.verticalCenter; button: "a"; style: pad.style; size: 28 }
                            Icon { visible: !pad.connected && !pad.deck; anchors.verticalCenter: parent.verticalCenter; name: tv.cur.installed ? "play" : "download"; size: 22; color: tv.tint.onPrimary }
                            Text { anchors.verticalCenter: parent.verticalCenter; text: playBtn.label; color: tv.tint.onPrimary; font.pixelSize: 21; font.weight: Font.DemiBold }
                        }
                        TapHandler { onTapped: tv.accept() }
                        HoverHandler { cursorShape: Qt.PointingHandCursor }
                    }
                    Rectangle {
                        height: 56; radius: 28
                        width: moreRow.implicitWidth + 40
                        color: Qt.alpha(theme.background, 0.55)
                        border.width: 1
                        border.color: Qt.alpha(theme.onSurface, 0.25)
                        Row {
                            id: moreRow
                            anchors.centerIn: parent
                            spacing: 10
                            PadButton { visible: pad.connected; anchors.verticalCenter: parent.verticalCenter; button: "x"; style: pad.style; size: 28 }
                            Icon { visible: !pad.connected; anchors.verticalCenter: parent.verticalCenter; name: "ellipsis"; size: 22; color: theme.onSurface }
                            Text { anchors.verticalCenter: parent.verticalCenter; text: "More"; color: theme.onSurface; font.pixelSize: 21; font.weight: Font.Medium }
                        }
                        TapHandler { onTapped: panel.show() }
                        HoverHandler { cursorShape: Qt.PointingHandCursor }
                    }
                }
            }
        }

        // Shelf label: which list this is, and where you are in it.
        RowLayout {
            Layout.fillWidth: true
            Layout.bottomMargin: -6
            spacing: 12
            Icon {
                name: tvLibrary.search !== "" ? "search" : ({ playing: "history", fav: "star", added: "gift", "": "library" })[tv.shelf.id] || "bookmark"
                size: 20
                color: tv.tint.primary
            }
            Text {
                text: tvLibrary.search !== "" ? "Results for \u201c" + tvLibrary.search + "\u201d" : tv.shelf.name
                color: theme.onSurface
                font.pixelSize: 20
                font.weight: Font.DemiBold
            }
            Rectangle {
                visible: tvLibrary.installedOnly
                height: 26; radius: 13
                width: instText.implicitWidth + 22
                color: Qt.alpha(tv.tint.primary, 0.2)
                border.width: 1; border.color: tv.tint.primary
                Text { id: instText; anchors.centerIn: parent; text: "Installed only"; color: theme.onSurface; font.pixelSize: 13; font.weight: Font.DemiBold }
            }
            Text {
                visible: grid.count > 0
                text: (grid.currentIndex + 1) + " of " + grid.count
                color: theme.onSurfaceVariant
                font.pixelSize: 17
            }
            Item { Layout.fillWidth: true }
            // The shelves above and below: up / down goes there.
            Text {
                visible: tvLibrary.search === "" && tv.shelfAt > 0
                text: "\u25B2  " + (tv.shelfList[tv.shelfAt - 1] || {}).name
                color: theme.onSurfaceVariant; opacity: 0.7
                font.pixelSize: 15
            }
            Text {
                visible: tvLibrary.search === "" && tv.shelfAt < tv.shelfList.length - 1
                text: "\u25BC  " + (tv.shelfList[tv.shelfAt + 1] || {}).name
                color: theme.onSurfaceVariant; opacity: 0.7
                font.pixelSize: 15
            }
        }

        // One row of covers along the bottom; left / right to browse.
        GridView {
            id: grid
            objectName: "tvGrid"
            Layout.fillWidth: true
            Layout.preferredHeight: Math.round(Math.max(200, tv.height * (peek.visible ? 0.29 : 0.34)))
            focus: true
            clip: false
            model: tvLibrary
            flow: GridView.FlowTopToBottom
            cellHeight: height
            cellWidth: Math.round(height / 1.46)
            cacheBuffer: cellWidth * 4
            keyNavigationEnabled: true
            boundsBehavior: Flickable.StopAtBounds
            highlightFollowsCurrentItem: false
            // Glide just far enough to keep the focused cover (and a bit of its neighbour) in view.
            // A cover you point at is already in view, so the row never shifts under the mouse.
            function reveal() {
                if (currentIndex < 0 || width <= 0) return
                const x = currentIndex * cellWidth
                const margin = Math.min(cellWidth * 0.5, width / 4)
                let to = contentX
                if (x - contentX < margin) to = x - margin
                else if (x + cellWidth - contentX > width - margin) to = x + cellWidth - width + margin
                to = Math.max(0, Math.min(to, contentWidth - width))
                if (Math.abs(to - contentX) > 1) { glide.to = to; glide.restart() }
            }
            // While a direction is held (auto-repeat) the row keeps up instead of easing behind.
            property bool fast: false
            NumberAnimation { id: glide; target: grid; property: "contentX"; duration: app.light ? 0 : grid.fast ? 80 : 220; easing.type: Easing.OutCubic }
            onWidthChanged: Qt.callLater(reveal)
            onCurrentIndexChanged: { tv.sync(); reveal(); if (tv.visible && !fast) app.uiSound("move") }
            function jump(to) { currentIndex = Math.max(0, Math.min(count - 1, to)) }
            readonly property int page: Math.max(1, Math.floor(width / cellWidth) - 1)
            onCountChanged: { if (currentIndex < 0 && count > 0) currentIndex = 0; tv.sync() }
            delegate: GameCard {
                id: tvCard
                required property int index
                width: grid.cellWidth
                height: grid.cellHeight
                theme: tv.tint
                cornerRadius: app.settingsMap.card_radius
                showBadge: false      // the focused game's store and ProtonDB rating are shown above the row
                showProtonDb: false
                showTitle: false
                dim: app.settingsMap.dim_uninstalled
                current: GridView.isCurrentItem
                // Pointing at a cover focuses it, so its artwork fills the screen.
                onHoveredChanged: if (hovered && grid.currentIndex !== index) grid.currentIndex = index
                onOpened: { grid.currentIndex = index; tv.sync(); panel.show() }
                onActivated: { grid.currentIndex = index; tv.sync(); tv.accept() }
                // A soft reflection on the shelf below (Settings > Appearance).
                Item {
                    visible: !!app.settingsMap.tv_reflection && !app.light && !peek.visible
                    x: 8; y: parent.height - 8
                    width: parent.width - 16
                    height: Math.round(parent.height * 0.1)
                    clip: true
                    opacity: tvCard.current ? 0.22 : 0.1
                    Behavior on opacity { NumberAnimation { duration: 200 } }
                    ArtImage {
                        width: parent.width
                        height: tvCard.height - 16
                        sources: tvCard.covers || []
                        sourceSize.width: 200
                        transform: Scale { origin.y: (tvCard.height - 16) / 2; yScale: -1 }
                    }
                    Rectangle {
                        anchors.fill: parent
                        gradient: Gradient {
                            GradientStop { position: 0.0; color: Qt.alpha(theme.background, 0.2) }
                            GradientStop { position: 1.0; color: theme.background }
                        }
                    }
                }
                // The focused game's animated cover, over its still one.
                RoundedArt {
                    anchors.fill: parent
                    anchors.margins: 8
                    radius: app.settingsMap.card_radius
                    visible: tvCard.current && tv.animOk && !!tv.anim.grid && animCover.status === Image.Ready
                    AnimatedImage {
                        id: animCover
                        anchors.fill: parent
                        source: tvCard.current && tv.animOk && tv.anim.grid ? tv.anim.grid : ""
                        asynchronous: true
                        fillMode: Image.PreserveAspectCrop
                        playing: tv.animOk
                    }
                }
            }
            Keys.onReturnPressed: tv.accept()
            Keys.onEnterPressed: tv.accept()
            Keys.onEscapePressed: {
                app.uiSound("back")
                if (tvLibrary.search !== "") tv.clearSearch()
                else if (tv.shelfAt > 0) tv.stepShelf(-tv.shelfAt)  // back to the top shelf, like Home
                else mainMenu.show()                              // home already: the menu (Exit TV mode is there)
            }
            Keys.onUpPressed: tv.stepShelf(-1)
            Keys.onDownPressed: tv.stepShelf(1)
            Keys.onPressed: event => {
                tv.wake()
                grid.fast = event.isAutoRepeat
                if ((event.key === Qt.Key_Left || event.key === Qt.Key_Right) && (event.modifiers & Qt.ShiftModifier)) {
                    grid.jump(currentIndex + (event.key === Qt.Key_Right ? page : -page)); event.accepted = true
                }
                else if (event.key === Qt.Key_Home) { grid.jump(0); event.accepted = true }
                else if (event.key === Qt.Key_End) { grid.jump(count - 1); event.accepted = true }
                else if (event.key === Qt.Key_F2) { panel.show(); event.accepted = true }
                else if (event.key === Qt.Key_F10) { mainMenu.show(); event.accepted = true }
                else if (event.key === Qt.Key_F9) { quickMenu.show(); event.accepted = true }
                else if (event.key === Qt.Key_F4 || event.key === Qt.Key_Slash) { tv.openSearch(""); event.accepted = true }
                else if (event.text && /^[a-z0-9]$/i.test(event.text) && !(event.modifiers & (Qt.ControlModifier | Qt.AltModifier))) {
                    tv.openSearch(event.text.toLowerCase()); event.accepted = true  // just start typing
                }
                else if (event.key === Qt.Key_F3 || (event.key === Qt.Key_Space && pad.deck && !pad.connected)) { tvLibrary.installedOnly = !tvLibrary.installedOnly; event.accepted = true }
                else if (event.key === Qt.Key_PageUp) { tv.cycleStore(-1); event.accepted = true }
                else if (event.key === Qt.Key_PageDown) { tv.cycleStore(1); event.accepted = true }
            }

            Text {
                visible: grid.count === 0
                anchors.centerIn: parent
                text: app.refreshing ? "Loading your libraries…" : "No games here"
                color: theme.onSurfaceVariant
                font.pixelSize: 26
            }
        }

        // The shelf below, previewed: smaller covers, dimmed. Down goes there.
        ColumnLayout {
            id: peek
            visible: !!tv.nextShelf && tv.height >= 900  // the Steam Deck (800 tall) keeps the room for the game
            Layout.fillWidth: true
            spacing: 8
            opacity: 0.55
            Text {
                text: "\u25BC  " + (tv.nextShelf ? tv.nextShelf.name : "")
                color: theme.onSurfaceVariant
                font.pixelSize: 16
                font.weight: Font.DemiBold
            }
            ListView {
                Layout.fillWidth: true
                Layout.preferredHeight: Math.round(Math.max(70, tv.height * 0.1))
                orientation: ListView.Horizontal
                interactive: false
                spacing: 10
                clip: true
                model: tvNextLibrary
                delegate: RoundedArt {
                    required property var covers
                    height: ListView.view.height
                    width: Math.round(height / 1.46)
                    radius: 8
                    ArtImage { anchors.fill: parent; sources: covers || []; sourceSize.width: 160 }
                }
            }
        }

        // Button hints: the connected controller's own glyphs, or keyboard keys; only the ones
        // that do something right now (no Jump in a short row, no Store with one store...).
        Row {
            Layout.alignment: Qt.AlignRight
            visible: tv.width >= 900
            spacing: 22
            Repeater {
                model: {
                    const play = tv.cur.key && !tv.cur.installed ? "Install" : "Play"
                    const jump = grid.count > grid.page + 1, stores = tv.storeIds.length > 2, shelves = tv.shelfList.length > 1
                    const all = pad.connected
                        ? [{ b: ["a"], t: play }, { b: ["start"], t: "Options" }, { b: ["guide"], t: "Menu" }, { b: ["y"], t: tvLibrary.installedOnly ? "All games" : "Installed only" },
                           shelves ? { b: ["\u2195"], t: "Shelf", pad: true } : null, jump ? { b: ["lt", "rt"], t: "Jump" } : null,
                           stores ? { b: ["lb", "rb"], t: "Store" } : null, { b: ["back"], t: "Search" },
                           { b: ["b"], t: tvLibrary.search ? "Clear search" : "Back" }]
                        : pad.deck  // Steam Deck in Desktop Mode: only the buttons Steam's desktop layout sends
                        ? [{ b: ["a"], t: play }, { k: "F2", t: "Options" }, { b: ["y"], t: "Installed only" }, { b: ["b"], t: "Back" }]
                        : [{ k: "Enter", t: play }, { k: "F2", t: "Options" }, { k: "F10", t: "Menu" }, { k: "F3", t: tvLibrary.installedOnly ? "All games" : "Installed only" },
                           shelves ? { k: "\u2191 \u2193", t: "Shelf" } : null, jump ? { k: "Shift \u2190/\u2192", t: "Jump" } : null,
                           stores ? { k: "PgUp / PgDn", t: "Store" } : null, { k: "Type", t: "Search" },
                           { k: "Esc", t: tvLibrary.search ? "Clear search" : "Back" }]
                    // Four at most: the rest are listed on a game's page (More).
                    return all.filter(h => h && !h.pad && ["Play", "Install", "Options", "More", "Menu", "Back", "Clear search"].indexOf(h.t) !== -1)
                }
                Hint { required property var modelData; hint: modelData }
            }
        }
    }

    // One button hint: the pad's glyphs or a keycap, and what it does.
    component Hint: Row {
        property var hint: ({})
        spacing: 8
        Repeater {
            model: hint.b || []
            PadButton { required property string modelData; button: modelData; style: pad.style; size: 26 }
        }
        Rectangle {  // keycap
            visible: !!hint.k
            height: 26; radius: 6
            width: hintKey.implicitWidth + 16
            color: Qt.alpha(theme.surfaceContainerHighest, 0.9)
            border.width: 1; border.color: theme.outlineVariant
            Text { id: hintKey; anchors.centerIn: parent; text: hint.k || ""; color: theme.onSurface; font.pixelSize: 12; font.weight: Font.DemiBold }
        }
        Text { anchors.verticalCenter: parent.verticalCenter; text: hint.t || ""; color: theme.onSurfaceVariant; font.pixelSize: 15 }
    }

    // The TV intro (Settings > Appearance, off by default): the corner lights up, the name
    // appears, a soft chime; then the home screen.
    property bool introDone: false
    function maybeIntro() { if (!introDone && app.settingsMap.tv_intro && !app.light) { introDone = true; intro.play() } }
    Rectangle {
        id: intro
        anchors.fill: parent
        z: 100
        color: theme.background
        visible: false
        function play() { visible = true; opacity = 1; app.uiSound("intro"); introAnim.restart() }
        BrandMark {
            id: introIcon
            anchors.centerIn: parent
            anchors.verticalCenterOffset: -40
            size: Math.round(tv.height * 0.22)
            opacity: 0; scale: 0.8
        }
        WordMark {
            id: introName
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: introIcon.bottom; anchors.topMargin: 28
            showIcon: false; size: Math.round(tv.height * 0.055)
            ink: "#fff3e0"; accent: "#ffb547"
            opacity: 0
        }
        SequentialAnimation {
            id: introAnim
            ParallelAnimation {
                NumberAnimation { target: introIcon; property: "opacity"; to: 1; duration: 600; easing.type: Easing.OutCubic }
                NumberAnimation { target: introIcon; property: "scale"; to: 1; duration: 900; easing.type: Easing.OutBack }
            }
            NumberAnimation { target: introName; property: "opacity"; to: 1; duration: 450 }
            PauseAnimation { duration: 700 }
            NumberAnimation { target: intro; property: "opacity"; to: 0; duration: 450; easing.type: Easing.InCubic }
            ScriptAction { script: { intro.visible = false; introIcon.opacity = 0; introIcon.scale = 0.8; introName.opacity = 0 } }
        }
        TapHandler { onTapped: { introAnim.stop(); intro.visible = false } }
        Keys.onPressed: event => { introAnim.stop(); intro.visible = false }
    }

    // Search keyboard: d-pad to a key, A types it, B deletes (or closes when empty),
    // View closes and keeps the results; a real keyboard types straight into it.
    // A soft dim behind the keyboard, so it reads as on top.
    Rectangle {
        anchors.fill: parent
        visible: tv.searching
        z: 4
        color: Qt.alpha("black", 0.45)
    }
    Rectangle {
        id: searchBox
        visible: tv.searching
        anchors { horizontalCenter: parent.horizontalCenter; top: parent.top; topMargin: 120 }
        width: Math.min(parent.width - 96, 760)
        height: searchCol.implicitHeight + 40
        radius: 24
        color: Qt.alpha(theme.surfaceContainer, 0.97)
        border.width: 1; border.color: theme.outlineVariant
        z: 5
        ColumnLayout {
            id: searchCol
            anchors { left: parent.left; right: parent.right; top: parent.top; margins: 20 }
            spacing: 14
            Rectangle {
                Layout.fillWidth: true
                height: 56; radius: 28
                color: theme.surfaceContainerHighest
                Icon { x: 20; anchors.verticalCenter: parent.verticalCenter; name: "search"; size: 22; color: theme.onSurfaceVariant }
                Text {
                    x: 54; anchors.verticalCenter: parent.verticalCenter
                    width: parent.width - 74
                    elide: Text.ElideLeft
                    text: tvLibrary.search !== "" ? tvLibrary.search : "Search your games"
                    color: tvLibrary.search !== "" ? theme.onSurface : theme.onSurfaceVariant
                    font.pixelSize: 22
                }
                Text {
                    anchors { right: parent.right; rightMargin: 22; verticalCenter: parent.verticalCenter }
                    text: grid.count + (grid.count === 1 ? " game" : " games")
                    color: theme.onSurfaceVariant; font.pixelSize: 16
                }
            }
            GridView {
                id: keys
                readonly property var letters: "abcdefghijklmnopqrstuvwxyz1234567890".split("").concat(["space", "del", "done"])
                Layout.fillWidth: true
                Layout.preferredHeight: Math.ceil(letters.length / 10) * cellHeight
                interactive: false
                cellWidth: Math.floor(width / 10)
                cellHeight: 58
                model: letters
                keyNavigationWraps: true
                delegate: Rectangle {
                    required property string modelData
                    required property int index
                    readonly property bool wide: modelData.length > 1
                    width: keys.cellWidth - 8; height: keys.cellHeight - 8
                    radius: 12
                    color: GridView.isCurrentItem && keys.activeFocus ? tv.tint.primary : theme.surfaceContainerHigh
                    Text {
                        anchors.centerIn: parent
                        text: ({ space: "\u2423", del: "\u232B", done: "\u2713" })[parent.modelData] || parent.modelData.toUpperCase()
                        color: parent.GridView.isCurrentItem && keys.activeFocus ? tv.tint.onPrimary : theme.onSurface
                        font.pixelSize: parent.wide ? 24 : 20
                        font.weight: Font.DemiBold
                    }
                    TapHandler { onTapped: { keys.currentIndex = parent.index; keys.press(parent.modelData) } }
                }
                function press(k) {
                    app.uiSound("move")
                    if (k === "done") tv.closeSearch(true)
                    else if (k === "del") tvLibrary.search = tvLibrary.search.slice(0, -1)
                    else tvLibrary.search = (tvLibrary.search + (k === "space" ? " " : k)).replace(/^ +/, "")
                    grid.currentIndex = 0; tv.sync()
                }
                Keys.onReturnPressed: press(letters[currentIndex])
                Keys.onEnterPressed: press(letters[currentIndex])
                Keys.onEscapePressed: {
                    if (tvLibrary.search !== "") press("del")
                    else { app.uiSound("back"); tv.closeSearch(false) }
                }
                Keys.onPressed: event => {
                    if (event.key === Qt.Key_F4) { tv.closeSearch(true); event.accepted = true }
                    else if (event.key === Qt.Key_Backspace) { press("del"); event.accepted = true }
                    else if (event.key === Qt.Key_Space) { press("space"); event.accepted = true }
                    else if (event.text && /^[a-z0-9]$/i.test(event.text)) { press(event.text.toLowerCase()); event.accepted = true }
                }
            }
        }
    }

    // Action panel: every choice for the focused game, one press each.
    Rectangle {
        anchors.fill: parent
        visible: panel.visible
        color: "#b0000000"
        // A MouseArea, not a TapHandler: it takes the click (and the hover), so the cover
        // underneath never gets it. A tap outside the panel closes it.
        MouseArea {
            anchors.fill: parent
            hoverEnabled: true
            acceptedButtons: Qt.AllButtons
            onClicked: panel.hide()
            onWheel: wheel => wheel.accepted = true
        }
    }
    Rectangle {
        id: panel
        property var rows: []
        property int armed: -1
        function show() { if (!tv.cur.key) return; app.uiSound("select"); rows = tv.buildActions(); armed = -1; list.currentIndex = 0; visible = true; list.forceActiveFocus() }
        function hide() { app.uiSound("back"); visible = false; grid.forceActiveFocus() }
        // Swallow clicks and hover on the panel's empty parts too (its rows sit on top of this).
        MouseArea {
            anchors.fill: parent
            z: -1
            hoverEnabled: true
            acceptedButtons: Qt.AllButtons
            onWheel: wheel => wheel.accepted = true
        }
        function run(i) {
            const a = rows[i]
            if (!a) return
            if (a.act === "uninstall" && armed !== i) { armed = i; return }
            armed = -1
            if (a.act === "play") { app.preferCopy(a.key); app.play(a.key) }
            else if (a.act === "install") { app.preferCopy(a.key); app.install(a.key) }
            else if (a.act === "update") app.update(a.key)
            else if (a.act === "cancel") app.cancel(a.key)
            else if (a.act === "uninstall") app.uninstall(a.key)
            else if (a.act === "hide" || a.act === "unhide") app.setHidden(a.key, a.act === "hide")
            else if (a.act === "fav") app.toggleFavourite(a.key)
            else if (a.act === "quit" || a.act === "kill") app.quitGame(a.key, a.act === "kill")
            else if (a.act === "status") {
                const order = ["", "playing", "want", "finished", "dropped"]
                app.setStatus(a.key, order[(order.indexOf(tv.cur.status || "") + 1) % order.length])
                rows = tv.buildActions()
                return  // stay open: press again for the next status
            }
            hide()
        }
        visible: false
        // The game's page: everything about it on the left, what to do on the right.
        anchors.fill: parent
        color: theme.background
        // The game's art behind the page, dimmed, so it feels like the game's own room.
        ArtImage {
            anchors.fill: parent
            visible: panel.visible && !app.light
            sources: tv.cur.heroes || []
            sourceSize.width: 1280
            opacity: status === Image.Ready ? 0.22 : 0
            Behavior on opacity { NumberAnimation { duration: 300 } }
        }
        Rectangle {
            anchors.fill: parent
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: Qt.alpha(theme.background, 0.55) }
                GradientStop { position: 0.6; color: Qt.alpha(theme.background, 0.75) }
                GradientStop { position: 1.0; color: Qt.alpha(theme.background, 0.95) }
            }
        }
        RowLayout {
            anchors.fill: parent
            anchors.margins: Math.round(Math.min(64, tv.width * 0.04))
            spacing: Math.round(Math.min(56, tv.width * 0.035))
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 14
            LogoTitle {
                Layout.fillWidth: true
                logos: tv.cur.logos || []
                title: tv.cur.title || ""
                color: theme.onSurface
                pixelSize: Math.round(Math.min(56, Math.max(34, tv.height * 0.05)))
                logoHeight: Math.round(Math.min(150, Math.max(70, tv.height * 0.13)))
                maxWidth: Math.min(width, 620)
            }
            Text {
                Layout.fillWidth: true
                text: [tv.cur.storeName || "", tv.cur.installed ? "Installed" : "Not installed",
                       tv.cur.key ? app.playedText(tv.cur.playtime, tv.cur.lastPlayed) : "",
                       tv.info.developer || "", tv.info.year || ""].filter(x => x).join("   \u00B7   ")
                color: theme.onSurfaceVariant; font.pixelSize: 18; wrapMode: Text.WordWrap
            }
            Flow {
                Layout.fillWidth: true
                spacing: 8
                Repeater {
                    model: tv.info.genres || []
                    Rectangle { required property string modelData; height: 30; radius: 15; width: pgT.implicitWidth + 26
                                color: "transparent"; border.width: 1; border.color: tv.tint.primary
                                Text { id: pgT; anchors.centerIn: parent; text: parent.modelData; color: theme.onSurface; font.pixelSize: 14 } }
                }
            }
            Flickable {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumHeight: 80
                clip: true
                contentHeight: pgAbout.implicitHeight
                boundsBehavior: Flickable.StopAtBounds
                Text { id: pgAbout; width: parent.width; text: tv.info.description || ""; color: theme.onSurface; opacity: 0.85
                       font.pixelSize: 18; lineHeight: 1.3; wrapMode: Text.WordWrap }
            }
            ListView {
                visible: (tv.info.screenshots || []).length > 0 && tv.height >= 640
                Layout.fillWidth: true
                Layout.preferredHeight: Math.round(Math.floor((width - 24) / 3) * 9 / 16)
                orientation: ListView.Horizontal
                spacing: 12
                interactive: false
                clip: true
                model: tv.info.screenshots || []
                delegate: RoundedArt {
                    required property var modelData
                    // three across, sized to the column (none cut off at the edge)
                    width: Math.floor((ListView.view.width - 24) / 3); height: Math.round(width * 9 / 16); radius: 10
                    Image { anchors.fill: parent; source: modelData.thumb || ""; fillMode: Image.PreserveAspectCrop; asynchronous: true }
                }
            }
        }
        ColumnLayout {
            Layout.preferredWidth: Math.min(480, tv.width * 0.36)
            Layout.fillHeight: true
            spacing: 18
            Text {  // the game's name is on the left already: here, what this column is for
                Layout.fillWidth: true
                text: "What would you like to do?"
                color: theme.onSurfaceVariant
                font.pixelSize: 18
            }
            Text {
                Layout.fillWidth: true
                visible: (tv.cur.copies || []).length > 1
                text: "You own this on " + (tv.cur.copies || []).length + " stores. Choose the launcher:"
                color: theme.onSurfaceVariant
                font.pixelSize: 16
                wrapMode: Text.WordWrap
            }
            ListView {
                id: list
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                spacing: 10
                model: panel.rows
                keyNavigationWraps: true
                delegate: Rectangle {
                    required property var modelData
                    required property int index
                    width: list.width
                    height: 60
                    radius: 14
                    color: ListView.isCurrentItem ? theme.primary : theme.surfaceContainerHigh
                    Icon {
                        anchors { verticalCenter: parent.verticalCenter; left: parent.left; leftMargin: 22 }
                        size: 22
                        name: ({ play: "play", install: "download", update: "arrow-up", cancel: "x", uninstall: "trash-2",
                                 fav: "star", status: "bookmark", hide: "eye-off", unhide: "eye", close: "x",
                                 quit: "x", kill: "x" })[parent.modelData.act] || "ellipsis"
                        color: parent.ListView.isCurrentItem ? theme.onPrimary
                               : parent.modelData.act === "uninstall" ? theme.error : theme.onSurfaceVariant
                    }
                    Text {
                        anchors { verticalCenter: parent.verticalCenter; left: parent.left; right: parent.right; leftMargin: 62; rightMargin: 22 }
                        text: panel.armed === parent.index ? "Press again to uninstall" : parent.modelData.label
                        color: parent.ListView.isCurrentItem ? theme.onPrimary
                               : parent.modelData.act === "uninstall" ? theme.error : theme.onSurface
                        font.pixelSize: 19
                        font.weight: Font.DemiBold
                        elide: Text.ElideRight
                    }
                    TapHandler { onTapped: { list.currentIndex = parent.index; panel.run(parent.index) } }
                }
                onCurrentIndexChanged: { panel.armed = -1; if (panel.visible) app.uiSound("move") }
                Keys.onReturnPressed: panel.run(currentIndex)
                Keys.onEnterPressed: panel.run(currentIndex)
                Keys.onEscapePressed: panel.hide()
                Keys.onLeftPressed: panel.hide()
            }
        }
        }
        // The other controls (the home screen only shows four), listed on the page.
        Text {
            anchors { left: parent.left; bottom: parent.bottom; margins: 30 }
            visible: tv.width >= 900
            text: pad.connected ? "Also:  \u2195 shelves   \u00B7   LT / RT jump   \u00B7   LB / RB store   \u00B7   Y installed only   \u00B7   \u29C9 search   \u00B7   Guide + A quick access"
                                : "Also:  \u2191\u2193 shelves   \u00B7   Shift+\u2190/\u2192 jump   \u00B7   PgUp/PgDn store   \u00B7   F3 installed only   \u00B7   F9 quick access"
            color: theme.outline; font.pixelSize: 14
        }
        // The page's own hints: only what works here.
        Row {
            anchors { right: parent.right; bottom: parent.bottom; margins: 28 }
            spacing: 22
            Repeater {
                model: pad.connected || pad.deck ? [{ b: ["a"], t: "Choose" }, { b: ["b"], t: "Back" }]
                                                 : [{ k: "Enter", t: "Choose" }, { k: "Esc", t: "Back" }]
                Hint { required property var modelData; hint: modelData }
            }
        }
    }

    // ------------------------------------------------------------ side menus (SteamOS style)
    // Guide: the main menu slides in from the left. Guide + A (or Share): quick access from the right.
    function mainRows() {
        return [
            { label: "Home", icon: "library", act: "home" },
            { label: "Search", icon: "search", act: "search" },
            { label: "Installed only", icon: "filter", act: "installed", on: tvLibrary.installedOnly },
            { label: "Next store", icon: "layout-grid", act: "store",
              value: (app.storesInfo.find(x => x.id === tvLibrary.storeFilter) || { name: "All games" }).name },
            { label: "Quick access", icon: "ellipsis", act: "quick" },
            { label: "Exit TV mode", icon: "log-out", act: "exit", group: "Power" },
            { label: "Quit Cornerplay", icon: "x", act: "quit", group: "Power", danger: true }
        ]
    }
    function quickRows() {
        const out = []
        for (const p of app.nowPlaying)
            out.push({ group: "Now playing", label: "Quit " + p.title, icon: "x", act: "quitgame", key: p.key })
        for (const j of app.jobList())
            out.push({ group: "Downloads", label: j.title, icon: j.job === "update" ? "arrow-up" : "download", act: "",
                       value: j.job === "queued" ? "Queued" : j.progress < 0 ? "Starting" : Math.floor(j.progress) + "%" })
        if (!out.length) out.push({ group: "Now playing", label: "Nothing running", icon: "gamepad-2", act: "" })
        out.push({ group: "Quick settings", label: "Sounds", icon: "sparkles", act: "set", setting: "tv_sounds", on: !!app.settingsMap.tv_sounds })
        out.push({ group: "Quick settings", label: "Trailers", icon: "play", act: "set", setting: "tv_trailers", on: !!app.settingsMap.tv_trailers })
        out.push({ group: "Quick settings", label: "Animated art", icon: "tv", act: "set", setting: "tv_animated", on: !!app.settingsMap.tv_animated })
        return out
    }
    SideSheet {
        id: mainMenu
        objectName: "tvMainMenu"
        side: "left"
        title: "Cornerplay"
        rowsFn: tv.mainRows
        onPicked: (row) => {
            if (row.act === "home") { hide(); if (tvLibrary.search !== "") tv.clearSearch(); if (tv.shelfAt > 0) tv.stepShelf(-tv.shelfAt) }
            else if (row.act === "search") { hide(); tv.openSearch("") }
            else if (row.act === "installed") { tvLibrary.installedOnly = !tvLibrary.installedOnly; refresh() }
            else if (row.act === "store") { tv.cycleStore(1); refresh() }
            else if (row.act === "quick") { hide(); quickMenu.show() }
            else if (row.act === "exit") { hide(); tv.exit() }
            else if (row.act === "quit") Qt.quit()
        }
    }
    SideSheet {
        id: quickMenu
        objectName: "tvQuickMenu"
        side: "right"
        title: topStatus.clock + (topStatus.batt.level !== undefined ? "   ·   " + topStatus.batt.level + "%" + (topStatus.batt.charging ? " ⚡" : "") : "")
        rowsFn: tv.quickRows
        Timer { interval: 1000; repeat: true; running: quickMenu.open; onTriggered: quickMenu.refresh() }  // download progress
        onPicked: (row) => {
            if (row.act === "quitgame") { app.quitGame(row.key, false); hide() }
            else if (row.act === "set") { app.setSetting(row.setting, !row.on); Qt.callLater(refresh) }
        }
    }

    // A menu that slides in from one side over a dimmed screen. A chooses, B (or the way
    // it came from) closes it. Rows: { label, icon, act, group, value, on (a switch), danger }.
    component SideSheet: Item {
        id: sheet
        property string side: "left"
        property string title: ""
        property var rowsFn: function() { return [] }
        property var rows: []
        property bool open: false
        signal picked(var row)
        anchors.fill: parent
        z: 90
        visible: open || slide.running || fadeIn.running
        function show() {
            if (open) { hide(); return }
            app.uiSound("select"); refresh(); sheetList.currentIndex = firstPickable(); open = true; sheetList.forceActiveFocus()
        }
        function hide() { if (!open) return; app.uiSound("back"); open = false; grid.forceActiveFocus() }
        function refresh() { const i = sheetList.currentIndex; rows = rowsFn(); sheetList.currentIndex = Math.min(Math.max(0, i), rows.length - 1) }
        function firstPickable() { const i = rows.findIndex(r => r.act); return Math.max(0, i) }
        readonly property real w: Math.round(Math.min(460, Math.max(320, tv.width * 0.3)))

        Rectangle {  // the dimmed screen behind; a click on it closes the menu
            anchors.fill: parent
            color: "black"
            opacity: sheet.open ? 0.5 : 0
            Behavior on opacity { enabled: !app.light; NumberAnimation { id: fadeIn; duration: 200 } }
            MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons; onClicked: sheet.hide(); onWheel: w => w.accepted = true }
        }
        Rectangle {
            id: pane
            width: sheet.w
            height: parent.height
            x: sheet.side === "left" ? (sheet.open ? 0 : -width) : (sheet.open ? parent.width - width : parent.width)
            Behavior on x { enabled: !app.light; NumberAnimation { id: slide; duration: 220; easing.type: Easing.OutCubic } }
            color: theme.surfaceContainerLow
            MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons; onWheel: w => w.accepted = true }
            Rectangle {  // a thin light edge on the side facing the screen
                width: 1; height: parent.height
                x: sheet.side === "left" ? parent.width - 1 : 0
                color: Qt.alpha("white", 0.08)
            }
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 28
                anchors.topMargin: 36
                spacing: 18
                Item {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 40
                    WordMark { visible: sheet.side === "left"; anchors.verticalCenter: parent.verticalCenter; size: 28 }
                    Text { visible: sheet.side !== "left"; anchors.verticalCenter: parent.verticalCenter
                           text: sheet.title; color: theme.onSurface; font.pixelSize: 24; font.weight: Font.Medium }
                }
                ListView {
                    id: sheetList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    spacing: 6
                    model: sheet.rows
                    keyNavigationWraps: true
                    boundsBehavior: Flickable.StopAtBounds
                    highlightMoveDuration: app.light ? 0 : 120
                    section.property: "group"
                    section.delegate: Text {
                        required property string section
                        width: ListView.view.width
                        height: section ? 44 : 0
                        visible: section !== ""
                        verticalAlignment: Text.AlignBottom
                        bottomPadding: 8
                        text: section.toUpperCase()
                        color: theme.outline; font.pixelSize: 13; font.weight: Font.DemiBold; font.letterSpacing: 1.4
                    }
                    delegate: Rectangle {
                        id: row
                        required property var modelData
                        required property int index
                        readonly property bool lit: ListView.isCurrentItem && sheetList.activeFocus
                        width: sheetList.width
                        height: 56
                        radius: 12
                        color: lit ? tv.tint.primary : "transparent"
                        Behavior on color { enabled: !app.light; ColorAnimation { duration: 100 } }
                        opacity: modelData.act ? 1 : 0.7
                        Icon {
                            anchors { left: parent.left; leftMargin: 16; verticalCenter: parent.verticalCenter }
                            name: row.modelData.icon || "ellipsis"; size: 22
                            color: row.lit ? tv.tint.onPrimary : row.modelData.danger ? theme.error : theme.onSurfaceVariant
                        }
                        Text {
                            anchors { left: parent.left; leftMargin: 54; right: rowEnd.left; rightMargin: 12; verticalCenter: parent.verticalCenter }
                            text: row.modelData.label
                            color: row.lit ? tv.tint.onPrimary : row.modelData.danger ? theme.error : theme.onSurface
                            font.pixelSize: 19; font.weight: Font.DemiBold
                            elide: Text.ElideRight
                        }
                        Item {
                            id: rowEnd
                            anchors { right: parent.right; rightMargin: 16; verticalCenter: parent.verticalCenter }
                            width: row.modelData.on !== undefined ? 44 : valueText.implicitWidth
                            height: 26
                            Text {
                                id: valueText
                                visible: row.modelData.on === undefined && !!row.modelData.value
                                anchors.verticalCenter: parent.verticalCenter
                                text: row.modelData.value || ""
                                color: row.lit ? tv.tint.onPrimary : theme.onSurfaceVariant
                                font.pixelSize: 16
                            }
                            Rectangle {  // a switch
                                visible: row.modelData.on !== undefined
                                anchors.fill: parent
                                radius: 13
                                color: row.modelData.on ? (row.lit ? tv.tint.onPrimary : tv.tint.primary) : Qt.alpha(theme.onSurface, 0.18)
                                Rectangle {
                                    width: 20; height: 20; radius: 10
                                    anchors.verticalCenter: parent.verticalCenter
                                    x: row.modelData.on ? parent.width - width - 3 : 3
                                    Behavior on x { enabled: !app.light; NumberAnimation { duration: 140 } }
                                    color: row.modelData.on ? (row.lit ? tv.tint.primary : tv.tint.onPrimary) : theme.onSurface
                                }
                            }
                        }
                        TapHandler { onTapped: { sheetList.currentIndex = row.index; if (row.modelData.act) sheet.picked(row.modelData) } }
                    }
                    onCurrentIndexChanged: if (sheet.open) app.uiSound("move")
                    // Skip rows that do nothing (headers of a sort, like "Nothing running").
                    function step(d) {
                        let i = currentIndex
                        for (let n = 0; n < count; n++) {
                            i = (i + d + count) % count
                            if (sheet.rows[i] && sheet.rows[i].act) { currentIndex = i; return }
                        }
                    }
                    Keys.onUpPressed: step(-1)
                    Keys.onDownPressed: step(1)
                    Keys.onReturnPressed: { const r = sheet.rows[currentIndex]; if (r && r.act) { app.uiSound("select"); sheet.picked(r) } }
                    Keys.onEnterPressed: { const r = sheet.rows[currentIndex]; if (r && r.act) { app.uiSound("select"); sheet.picked(r) } }
                    Keys.onEscapePressed: sheet.hide()
                    Keys.onPressed: event => {
                        // The way it came from closes it: Guide for the main menu, Guide + A for quick access,
                        // or the stick pushed back toward the edge.
                        if ((event.key === Qt.Key_F10 && sheet.side === "left") || (event.key === Qt.Key_F9 && sheet.side === "right")
                            || (event.key === Qt.Key_Left && sheet.side === "left") || (event.key === Qt.Key_Right && sheet.side === "right")) {
                            sheet.hide(); event.accepted = true
                        } else if (event.key === Qt.Key_F10 || event.key === Qt.Key_F9) {
                            sheet.hide(); (event.key === Qt.Key_F10 ? mainMenu : quickMenu).show(); event.accepted = true
                        }
                    }
                }
                Row {
                    spacing: 22
                    Repeater {
                        model: pad.connected || pad.deck ? [{ b: ["a"], t: "Choose" }, { b: ["b"], t: "Back" }]
                                                         : [{ k: "Enter", t: "Choose" }, { k: "Esc", t: "Back" }]
                        Hint { required property var modelData; hint: modelData }
                    }
                }
            }
        }
    }
}
