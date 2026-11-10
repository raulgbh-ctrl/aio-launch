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
    Timer { id: infoTimer; interval: 350; onTriggered: tv.info = tv.infoKey ? app.gameDetails(tv.infoKey) : ({}) }
    onCurChanged: {
        if ((cur.key || "") === infoKey) return  // same game, just refreshed
        infoKey = cur.key || ""
        gameAccent = cur.key ? app.gameColour(cur.key) : ""
        info = ({})
        infoTimer.restart()
    }
    readonly property var storeIds: [""].concat(app.storesInfo.map(s => s.id))

    function sync() { cur = app.game(library.keyAt(grid.currentIndex)) }
    function cycleStore(step) {
        app.uiSound("move")
        const i = storeIds.indexOf(library.storeFilter)
        library.storeFilter = storeIds[(i + step + storeIds.length) % storeIds.length]
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
        out.push({ label: cur.hidden ? "Unhide game" : "Hide game", act: cur.hidden ? "unhide" : "hide", key: cur.key })
        out.push({ label: "Close", act: "close", key: "" })
        return out
    }

    function grab() { grid.forceActiveFocus(); sync() }
    onVisibleChanged: if (visible) grab()
    Component.onCompleted: if (visible) Qt.callLater(grab)
    Connections {
        target: app
        function onGameChanged(key) { tv.sync(); if (panel.visible) panel.rows = tv.buildActions() }
        function onGameColourReady(key, colour) { if (key === tv.cur.key) tv.gameAccent = colour }
        function onDetailsReady(key, d) { if (key === tv.infoKey) tv.info = d }
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
        Loader {
            anchors.fill: parent
            active: typeof canPlayVideo !== "undefined" && canPlayVideo && app.settingsMap.tv_trailers
                    && !app.light && tv.visible && tv.trailerUrl !== ""
                    && Qt.application.state === Qt.ApplicationActive  // never behind a running game
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
                GradientStop { position: 0.0; color: Qt.alpha(theme.background, 0.88) }
                GradientStop { position: 0.38; color: Qt.alpha(theme.background, 0.45) }
                GradientStop { position: 0.7; color: Qt.alpha(theme.background, 0.0) }
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
            Text {
                textFormat: Text.StyledText
                text: "Corner<b><font color=\"" + tv.tint.primary + "\">play</font></b>"
                color: theme.onSurface; font.pixelSize: 30; font.weight: Font.Light; Layout.rightMargin: 20
            }
            Repeater {
                model: tv.storeIds
                Rectangle {
                    required property string modelData
                    readonly property bool active: library.storeFilter === modelData
                    readonly property var info: app.storesInfo.find(s => s.id === modelData) || ({ name: "All games", color: "" })
                    implicitWidth: tabRow.implicitWidth + 36
                    implicitHeight: 46
                    radius: 23
                    color: active ? tv.tint.primary : "transparent"
                    border.width: active ? 0 : 1
                    border.color: theme.outlineVariant
                    Row {
                        id: tabRow
                        anchors.centerIn: parent
                        spacing: 9
                        StoreIcon {
                            visible: parent.parent.modelData !== ""
                            anchors.verticalCenter: parent.verticalCenter
                            size: 20
                            store: parent.parent.modelData
                            color: parent.parent.active ? tv.tint.onPrimary : (parent.parent.info.color || theme.onSurfaceVariant)
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
                    TapHandler { onTapped: { library.storeFilter = parent.modelData; grid.currentIndex = 0; tv.sync() } }
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
                    visible: played !== ""
                    text: played
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
                    Layout.maximumWidth: 760
                    visible: text !== "" && infoArea.roomForText
                    text: tv.info.description || ""
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
                        readonly property string label: tv.cur.job ? ({ install: "Installing", update: "Updating", dlc: "Installing DLC" }[tv.cur.job] || "Removing")
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
            Text {
                text: (library.storeFilter ? (app.storesInfo.find(s => s.id === library.storeFilter) || {}).name || "Library" : "Library")
                color: theme.onSurface
                font.pixelSize: 20
                font.weight: Font.DemiBold
            }
            Rectangle {
                visible: library.installedOnly
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
        }

        // One row of covers along the bottom; left / right to browse.
        GridView {
            id: grid
            objectName: "tvGrid"
            Layout.fillWidth: true
            Layout.preferredHeight: Math.round(Math.max(220, tv.height * 0.34))
            focus: true
            clip: false
            model: library
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
            }
            Keys.onReturnPressed: tv.accept()
            Keys.onEnterPressed: tv.accept()
            Keys.onEscapePressed: { app.uiSound("back"); tv.exit() }
            Keys.onPressed: event => {
                grid.fast = event.isAutoRepeat
                if ((event.key === Qt.Key_Left || event.key === Qt.Key_Right) && (event.modifiers & Qt.ShiftModifier)) {
                    grid.jump(currentIndex + (event.key === Qt.Key_Right ? page : -page)); event.accepted = true
                }
                else if (event.key === Qt.Key_Home) { grid.jump(0); event.accepted = true }
                else if (event.key === Qt.Key_End) { grid.jump(count - 1); event.accepted = true }
                else if (event.key === Qt.Key_F2) { panel.show(); event.accepted = true }
                else if (event.key === Qt.Key_F3 || (event.key === Qt.Key_Space && pad.deck && !pad.connected)) { library.installedOnly = !library.installedOnly; event.accepted = true }
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

        // Button hints: the connected controller's own glyphs, or keyboard keys.
        Row {
            Layout.alignment: Qt.AlignRight
            visible: tv.width >= 900
            spacing: 22
            Repeater {
                model: pad.connected
                       ? [{ b: ["a"], t: "Play" }, { b: ["x"], t: "Actions" }, { b: ["y"], t: "Installed only" },
                          { b: ["lt", "rt"], t: "Jump" }, { b: ["lb", "rb"], t: "Store" }, { b: ["b"], t: "Back" }]
                       : pad.deck  // Steam Deck in Desktop Mode: only the buttons Steam's desktop layout sends
                       ? [{ b: ["a"], t: "Play" }, { k: "F2", t: "Actions" }, { b: ["y"], t: "Installed only" },
                          { b: ["b"], t: "Back" }]
                       : [{ k: "Enter", t: "Play" }, { k: "F2", t: "Actions" }, { k: "F3", t: "Installed only" },
                          { k: "Shift ←/→", t: "Jump" }, { k: "PgUp / PgDn", t: "Store" }, { k: "Esc", t: "Back" }]
                Row {
                    required property var modelData
                    spacing: 8
                    Repeater {
                        model: modelData.b || []
                        PadButton { required property string modelData; button: modelData; style: pad.style; size: 26 }
                    }
                    Rectangle {  // keycap
                        visible: !!modelData.k
                        height: 26; radius: 6
                        width: keyText.implicitWidth + 16
                        color: Qt.alpha(theme.surfaceContainerHighest, 0.9)
                        border.width: 1; border.color: theme.outlineVariant
                        Text { id: keyText; anchors.centerIn: parent; text: modelData.k || ""; color: theme.onSurface; font.pixelSize: 12; font.weight: Font.DemiBold }
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: modelData.t
                        color: theme.onSurfaceVariant
                        font.pixelSize: 15
                    }
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
            hide()
        }
        visible: false
        anchors { right: parent.right; top: parent.top; bottom: parent.bottom }
        width: Math.min(520, parent.width * 0.42)
        color: theme.surfaceContainer
        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 40
            spacing: 18
            Text {
                Layout.fillWidth: true
                text: tv.cur.title || ""
                color: theme.onSurface
                font.pixelSize: 28
                font.weight: Font.Bold
                wrapMode: Text.WordWrap
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
                    Text {
                        anchors { verticalCenter: parent.verticalCenter; left: parent.left; right: parent.right; margins: 22 }
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
}
