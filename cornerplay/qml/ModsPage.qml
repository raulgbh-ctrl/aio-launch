import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// A game's mods (mods.py): what is installed, switched on or off for the active profile, with
// updates; and Find mods, from Thunderstore or Nexus Mods. Changes go into the game at once.
KDialog {
    id: page
    property string gameKey: ""
    property var v: ({})            // app.modsReady's view
    property var found: []
    property string query: ""
    property bool searching: false
    property string busy: ""
    property int tab: 0             // 0 installed, 1 find
    heading: v.game ? qsTr("Mods for %1").arg(v.game) : qsTr("Mods")
    headingIcon: "sparkles"
    width: Math.min(parent ? parent.width - 80 : 900, 920)
    height: Math.min(parent ? parent.height - 80 : 760, 780)
    closePolicy: Popup.CloseOnEscape

    function show(key) {
        gameKey = key; v = ({}); found = []; query = ""; busy = ""; tab = 0
        app.loadMods(key)
        open()
    }
    function search() {
        searching = true
        app.searchMods(gameKey, searchField.text)
    }
    readonly property bool nexus: v.source === "nexus"
    readonly property string sourceName: nexus ? "Nexus Mods" : "Thunderstore"

    Connections {
        target: app
        function onModsReady(key, view) { if (key === page.gameKey) page.v = view }
        function onModSearchReady(key, q, rows) { if (key === page.gameKey) { page.found = rows; page.searching = false } }
        function onModBusy(key, text) {
            if (key !== page.gameKey) return
            const was = page.busy
            page.busy = text
            if (!text && was && page.tab === 1 && page.found.length) page.search()  // refresh "Installed" marks
        }
    }

    component Pill: Rectangle {
        property string text
        property color tone: page.theme.outline
        radius: 6; implicitHeight: 20; implicitWidth: pillText.implicitWidth + 12
        color: "transparent"; border.width: 1; border.color: tone
        Text { id: pillText; anchors.centerIn: parent; text: parent.text; color: parent.tone; font.pixelSize: 10; font.weight: Font.DemiBold }
    }

    contentItem: ColumnLayout {
        spacing: 12

        // Profile, and the state of things
        RowLayout {
            Layout.fillWidth: true
            spacing: 10
            Text { text: qsTr("Profile"); color: theme.onSurfaceVariant; font.pixelSize: 13 }
            KCombo {
                id: profileBox
                theme: page.theme
                Layout.preferredWidth: 200
                model: (page.v.profiles || []).map(p => ({ label: p, value: p }))
                onModelChanged: select(page.v.profile)
                onActivated: if (currentValue !== page.v.profile) app.modProfile(page.gameKey, "use", currentValue)
            }
            KButton {
                theme: page.theme; iconName: "plus"; text: qsTr("New")
                onClicked: { newName.text = ""; newProfile.open() }
            }
            KButton {
                theme: page.theme; iconName: "trash-2"
                visible: (page.v.profiles || []).length > 1
                ToolTip.visible: hovered; ToolTip.text: qsTr("Delete this profile")
                onClicked: app.modProfile(page.gameKey, "delete", page.v.profile)
            }
            Item { Layout.fillWidth: true }
            Text {
                visible: page.busy !== ""
                text: page.busy + "…"
                color: theme.primary; font.pixelSize: 13; font.weight: Font.DemiBold
            }
            KButton {
                theme: page.theme
                visible: page.busy === "" && (page.v.enabledCount || 0) > 0 && page.v.installed
                text: qsTr("Play without mods")
                iconName: "eye-off"
                ToolTip.visible: hovered
                ToolTip.text: qsTr("Takes every mod file out of the game folder; switching any mod on puts them back")
                onClicked: app.turnOffMods(page.gameKey)
            }
        }
        Text {
            Layout.fillWidth: true
            visible: page.v.playing === true
            text: qsTr("The game is running: close it to change its mods.")
            color: theme.error; font.pixelSize: 13; wrapMode: Text.WordWrap
        }
        Text {
            Layout.fillWidth: true
            visible: page.v.gid !== undefined && !page.v.installed
            text: qsTr("The game isn't installed on this PC: you can pick mods now, and they go into the game once it is.")
            color: theme.onSurfaceVariant; font.pixelSize: 13; wrapMode: Text.WordWrap
        }
        // Once-only setup the game needs (a mod loader, a launch option)
        Repeater {
            model: page.v.notes || []
            Rectangle {
                required property var modelData
                Layout.fillWidth: true
                implicitHeight: noteRow.implicitHeight + 20
                radius: 10
                color: theme.surfaceContainer
                RowLayout {
                    id: noteRow
                    anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; margins: 12 }
                    spacing: 10
                    Icon { name: "info"; size: 16; color: theme.primary }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 6
                        Text { Layout.fillWidth: true; text: modelData.text; color: theme.onSurface; font.pixelSize: 13; wrapMode: Text.WordWrap }
                        Text {
                            visible: !!modelData.copy
                            text: modelData.copy || ""
                            color: theme.primary; font.family: "monospace"; font.pixelSize: 12
                        }
                    }
                    KButton {
                        theme: page.theme
                        visible: !!modelData.copy || !!modelData.url
                        text: modelData.copy ? qsTr("Copy") : qsTr("Open")
                        iconName: modelData.copy ? "copy" : "external-link"
                        onClicked: modelData.copy ? app.copyText(modelData.copy) : app.openUrl(modelData.url)
                    }
                }
            }
        }

        // Tabs
        RowLayout {
            Layout.fillWidth: true
            spacing: 6
            Repeater {
                model: [qsTr("Installed") + ((page.v.mods || []).length ? "  ·  " + page.v.mods.length : ""),
                        qsTr("Find mods on ") + page.sourceName]
                Rectangle {
                    required property string modelData
                    required property int index
                    radius: 10; implicitHeight: 34; implicitWidth: tabText.implicitWidth + 28
                    color: page.tab === index ? theme.primaryContainer : (tabHover.hovered ? theme.surfaceContainerHigh : "transparent")
                    Text { id: tabText; anchors.centerIn: parent; text: modelData; font.pixelSize: 13; font.weight: Font.DemiBold
                           color: page.tab === index ? theme.onPrimaryContainer : theme.onSurfaceVariant }
                    HoverHandler { id: tabHover; cursorShape: Qt.PointingHandCursor }
                    TapHandler {
                        onTapped: {
                            page.tab = index
                            if (index === 1 && !page.found.length && !page.searching) page.search()
                        }
                    }
                }
            }
            Item { Layout.fillWidth: true }
        }

        // --- Installed ---------------------------------------------------------------
        ListView {
            id: installedList
            visible: page.tab === 0
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            spacing: 6
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: KScrollBar { }
            model: page.v.mods || []
            Text {
                anchors.centerIn: parent
                width: parent.width - 40
                visible: installedList.count === 0 && page.v.gid !== undefined
                horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap
                text: qsTr("No mods yet. Find some on %1: they install with whatever they need.").arg(page.sourceName)
                color: theme.onSurfaceVariant; font.pixelSize: 14
            }
            delegate: Rectangle {
                id: modRow
                required property var modelData
                width: installedList.width - 12
                implicitHeight: 64
                radius: 10
                color: rowHover.hovered ? theme.surfaceContainerHigh : theme.surfaceContainer
                opacity: modelData.enabled ? 1 : 0.7
                HoverHandler { id: rowHover }
                RowLayout {
                    anchors { fill: parent; leftMargin: 10; rightMargin: 10 }
                    spacing: 12
                    RoundedArt {
                        Layout.preferredWidth: 44; Layout.preferredHeight: 44; radius: 8
                        ArtImage { anchors.fill: parent; sources: modRow.modelData.icon ? [modRow.modelData.icon] : []; sourceSize.width: 88 }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 3
                        RowLayout {
                            spacing: 8
                            Text { text: modRow.modelData.name; color: theme.onSurface; font.pixelSize: 14; font.weight: Font.DemiBold; elide: Text.ElideRight; Layout.maximumWidth: 360 }
                            Pill { visible: modRow.modelData.auto; text: qsTr("DEPENDENCY") }
                            Pill { visible: modRow.modelData.update !== ""; text: qsTr("UPDATE"); tone: theme.primary }
                        }
                        Text {
                            Layout.fillWidth: true
                            text: [modRow.modelData.author ? qsTr("by ") + modRow.modelData.author : "", modRow.modelData.version ? "v" + modRow.modelData.version : "",
                                   modRow.modelData.neededBy.length ? qsTr("needed by ") + modRow.modelData.neededBy.join(", ") : "",
                                   modRow.modelData.options.length ? qsTr("options: ") + modRow.modelData.options.join(", ") : ""].filter(x => x).join("  ·  ")
                            color: theme.outline; font.pixelSize: 12; elide: Text.ElideRight
                        }
                    }
                    KButton {
                        theme: page.theme; primary: true
                        visible: modRow.modelData.update !== ""
                        enabled: page.busy === ""
                        text: qsTr("Update to ") + modRow.modelData.update
                        onClicked: app.updateMod(page.gameKey, modRow.modelData.id)
                    }
                    KButton {
                        theme: page.theme; iconName: "external-link"
                        ToolTip.visible: hovered; ToolTip.text: qsTr("Its page on ") + (modRow.modelData.source === "nexus" ? "Nexus Mods" : "Thunderstore")
                        onClicked: app.openUrl(modRow.modelData.url)
                    }
                    KButton {
                        theme: page.theme; iconName: "trash-2"; danger: true
                        enabled: page.busy === "" && !page.v.playing
                        ToolTip.visible: hovered; ToolTip.text: qsTr("Remove")
                        onClicked: app.removeMod(page.gameKey, modRow.modelData.id)
                    }
                    Switch {
                        id: modSwitch
                        checked: modRow.modelData.enabled
                        enabled: page.busy === "" && !page.v.playing
                        onToggled: app.toggleMod(page.gameKey, modRow.modelData.id, checked)
                        indicator: Rectangle {
                            implicitWidth: 40; implicitHeight: 22; radius: 11
                            y: parent.height / 2 - height / 2
                            color: modSwitch.checked ? theme.primary : theme.surfaceContainerHighest
                            Rectangle {
                                x: modSwitch.checked ? parent.width - width - 3 : 3
                                anchors.verticalCenter: parent.verticalCenter
                                width: 16; height: 16; radius: 8
                                color: modSwitch.checked ? theme.onPrimary : theme.outline
                                Behavior on x { NumberAnimation { duration: 120 } }
                            }
                        }
                    }
                }
            }
        }

        // --- Find --------------------------------------------------------------------
        ColumnLayout {
            visible: page.tab === 1
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 10

            // Nexus Mods: the API key (downloads), and taking its "Mod Manager Download" links
            Rectangle {
                visible: page.nexus
                Layout.fillWidth: true
                implicitHeight: nexusCol.implicitHeight + 20
                radius: 10
                color: theme.surfaceContainer
                ColumnLayout {
                    id: nexusCol
                    anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; margins: 12 }
                    spacing: 8
                    Text {
                        Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 13
                        color: theme.onSurface
                        text: page.v.nexus && page.v.nexus.hasKey
                              ? qsTr("Nexus Mods: signed in as %1").arg(page.v.nexus.name) + (page.v.nexus.premium
                                    ? qsTr(" (Premium: Install downloads straight away).")
                                    : qsTr(". Free accounts download from the mod's page: Install opens it, then press “Mod Manager Download”."))
                              : qsTr("Searching needs nothing. To download, paste your personal API key from your Nexus Mods account (Settings › API Keys, at the bottom: Personal API Key).")
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        KField {
                            id: nexusKey
                            theme: page.theme
                            Layout.fillWidth: true
                            visible: !(page.v.nexus && page.v.nexus.hasKey)
                            placeholderText: qsTr("Nexus Mods API key")
                            echoMode: TextInput.Password
                            onAccepted: app.setNexusKey(page.gameKey, text)
                        }
                        KButton {
                            theme: page.theme
                            visible: !(page.v.nexus && page.v.nexus.hasKey)
                            text: qsTr("Get my key"); iconName: "external-link"
                            onClicked: app.openUrl("https://www.nexusmods.com/settings/api-keys")
                        }
                        KButton {
                            theme: page.theme; primary: true
                            visible: !(page.v.nexus && page.v.nexus.hasKey)
                            enabled: nexusKey.text.trim() !== ""
                            text: qsTr("Save")
                            onClicked: app.setNexusKey(page.gameKey, nexusKey.text)
                        }
                        KButton {
                            id: nxmButton
                            theme: page.theme
                            property bool handled: false
                            visible: !!(page.v.nexus && page.v.nexus.hasKey && !page.v.nexus.premium)
                            text: handled ? qsTr("Nexus downloads open in Cornerplay") : qsTr("Open Nexus downloads in Cornerplay")
                            iconName: handled ? "check" : "external-link"
                            enabled: !handled
                            Component.onCompleted: handled = app.nxmHandled()
                            onClicked: { app.handleNxmLinks(); handled = app.nxmHandled() }
                        }
                        Item { Layout.fillWidth: true; visible: !!(page.v.nexus && page.v.nexus.hasKey) }
                        KButton {
                            theme: page.theme
                            visible: !!(page.v.nexus && page.v.nexus.hasKey)
                            text: qsTr("Remove key")
                            onClicked: app.setNexusKey(page.gameKey, "")
                        }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                KField {
                    id: searchField
                    theme: page.theme
                    Layout.fillWidth: true
                    iconName: "search"
                    placeholderText: qsTr("Search %1 (empty: the most downloaded)").arg(page.sourceName)
                    onAccepted: page.search()
                }
                KButton { theme: page.theme; primary: true; text: qsTr("Search"); onClicked: page.search() }
            }
            ListView {
                id: foundList
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                spacing: 6
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: KScrollBar { }
                model: page.found
                Text {
                    anchors.centerIn: parent
                    visible: foundList.count === 0
                    text: page.searching ? qsTr("Searching…") : qsTr("Nothing found")
                    color: theme.onSurfaceVariant; font.pixelSize: 14
                }
                delegate: Rectangle {
                    id: hit
                    required property var modelData
                    width: foundList.width - 12
                    implicitHeight: 76
                    radius: 10
                    color: hitHover.hovered ? theme.surfaceContainerHigh : theme.surfaceContainer
                    HoverHandler { id: hitHover }
                    RowLayout {
                        anchors { fill: parent; leftMargin: 10; rightMargin: 10 }
                        spacing: 12
                        RoundedArt {
                            Layout.preferredWidth: page.nexus ? 96 : 56; Layout.preferredHeight: 56; radius: 8
                            ArtImage { anchors.fill: parent; sources: hit.modelData.icon ? [hit.modelData.icon] : []; sourceSize.width: 192 }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 3
                            Text { Layout.fillWidth: true; text: hit.modelData.name; color: theme.onSurface; font.pixelSize: 14; font.weight: Font.DemiBold; elide: Text.ElideRight }
                            Text { Layout.fillWidth: true; text: hit.modelData.description; color: theme.onSurfaceVariant; font.pixelSize: 12; elide: Text.ElideRight; maximumLineCount: 2; wrapMode: Text.WordWrap }
                            Text {
                                text: qsTr("by ") + hit.modelData.author + "  ·  " + Number(hit.modelData.downloads).toLocaleString(Qt.locale(), "f", 0) + qsTr(" downloads")
                                color: theme.outline; font.pixelSize: 11
                            }
                        }
                        KButton {
                            theme: page.theme; iconName: "external-link"
                            ToolTip.visible: hovered; ToolTip.text: qsTr("Its page")
                            onClicked: app.openUrl(hit.modelData.url)
                        }
                        KButton {
                            theme: page.theme
                            primary: !hit.modelData.installed
                            enabled: !hit.modelData.installed && page.busy === "" && !page.v.playing
                            text: hit.modelData.installed ? qsTr("Installed") : qsTr("Install")
                            iconName: hit.modelData.installed ? "check" : "download"
                            onClicked: app.installMod(page.gameKey, hit.modelData.id)
                        }
                    }
                }
            }
        }
    }

    KDialog {
        id: newProfile
        theme: page.theme
        heading: qsTr("New profile")
        width: 420
        onOpened: newName.forceActiveFocus()
        contentItem: ColumnLayout {
            spacing: 12
            KField { id: newName; theme: page.theme; Layout.fillWidth: true; placeholderText: qsTr("Name, e.g. Co-op or Vanilla+")
                     onAccepted: if (text.trim()) { app.modProfile(page.gameKey, "copy", text); newProfile.close() } }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                KButton { theme: page.theme; text: qsTr("Start empty"); enabled: newName.text.trim() !== ""
                          onClicked: { app.modProfile(page.gameKey, "new", newName.text); newProfile.close() } }
                KButton { theme: page.theme; primary: true; text: qsTr("Copy this one"); enabled: newName.text.trim() !== ""
                          onClicked: { app.modProfile(page.gameKey, "copy", newName.text); newProfile.close() } }
            }
        }
    }
}
