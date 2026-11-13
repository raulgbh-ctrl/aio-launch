import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// Humble Bundle's shop window, on the Humble Bundle page: this month's Humble Choice games and the
// game bundles on sale, with their prices. A click opens the page on humblebundle.com.
Column {
    id: shop
    required property var theme
    property bool shown: false
    readonly property var data_: app.humbleShop
    readonly property bool hasChoice: (data_.games || []).length > 0
    readonly property bool hasBundles: (data_.bundles || []).length > 0
    // How each Choice game is delivered, as Humble names it.
    readonly property var stores: ({ steam: qsTr("Steam key"), blizzard: qsTr("Battle.net key"), epic: qsTr("Epic Games key"),
                                      gog: qsTr("GOG key"), origin: qsTr("EA app key"), uplay: qsTr("Ubisoft Connect key"),
                                      external_key: qsTr("Code for another service"), download: qsTr("DRM-free download") })

    visible: shown && (hasChoice || hasBundles)
    height: visible ? implicitHeight : 0
    topPadding: 4
    bottomPadding: 20
    spacing: 22

    onShownChanged: if (shown) app.loadHumbleShop()
    Component.onCompleted: if (shown) app.loadHumbleShop()

    component Head: RowLayout {
        id: head
        property string icon
        property string title
        property string note: ""
        property string action
        signal picked()
        x: 8
        width: shop.width - 16
        spacing: 8
        Icon { name: head.icon; size: 15; color: shop.theme.primary }
        Text { text: head.title; color: shop.theme.onSurface; font.pixelSize: 15; font.weight: Font.DemiBold }
        Text { visible: head.note !== ""; text: "·  " + head.note; color: shop.theme.outline; font.pixelSize: 13 }
        Item { Layout.fillWidth: true }
        Text {
            text: head.action + "  ↗"
            color: headHover.hovered ? shop.theme.primary : shop.theme.onSurfaceVariant
            font.pixelSize: 13; font.weight: Font.DemiBold
            HoverHandler { id: headHover; cursorShape: Qt.PointingHandCursor }
            TapHandler { onTapped: head.picked() }
        }
    }

    // A tile: wide picture on top, then up to three lines of text.
    component Tile: Rectangle {
        id: tile
        property string image
        property string title
        property string line1
        property color line1Color: shop.theme.primary
        property string line2: ""
        property string badge: ""
        property string url
        property bool opensPage: true   // false: picked() instead (a bundle opens its breakdown)
        signal picked()
        width: 268; height: 236
        radius: 12
        color: shop.theme.surfaceContainerHigh
        RoundedArt {
            id: pic
            width: parent.width; height: 151
            radius: tile.radius
            ArtImage { anchors.fill: parent; sources: tile.image ? [tile.image] : []; sourceSize.width: 536 }
        }
        Rectangle {
            visible: tile.badge !== ""
            anchors { top: parent.top; right: parent.right; margins: 8 }
            radius: 8; height: 24; width: badgeText.implicitWidth + 16
            color: shop.theme.primary
            Text { id: badgeText; anchors.centerIn: parent; text: tile.badge; color: shop.theme.onPrimary; font.pixelSize: 12; font.weight: Font.DemiBold }
        }
        Column {
            anchors { left: parent.left; right: parent.right; top: pic.bottom; margins: 12; topMargin: 9 }
            spacing: 4
            Text {
                width: parent.width
                text: tile.title
                font.family: app.titleFamily
                color: shop.theme.onSurface
                font.pixelSize: 14; font.weight: Font.DemiBold
                elide: Text.ElideRight
            }
            Text { width: parent.width; text: tile.line1; color: tile.line1Color; font.pixelSize: 13; font.weight: Font.DemiBold; elide: Text.ElideRight }
            Text { width: parent.width; visible: tile.line2 !== ""; text: tile.line2; color: shop.theme.outline; font.pixelSize: 12; elide: Text.ElideRight }
        }
        Rectangle {
            anchors.fill: parent; radius: tile.radius; color: "transparent"; z: 1
            border.width: tileHover.hovered ? 2 : 0
            border.color: shop.theme.primary
        }
        HoverHandler { id: tileHover; cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: tile.opensPage ? app.openUrl(tile.url) : tile.picked() }
    }

    // --- Humble Choice ---------------------------------------------------------
    Column {
        visible: shop.hasChoice
        width: shop.width
        spacing: 10
        Head {
            icon: "gift"
            title: qsTr("Humble Choice") + (shop.data_.month ? "  ·  " + shop.data_.month : "")
            note: shop.data_.price ? qsTr("%1 games for %2 a month").arg((shop.data_.games || []).length).arg(shop.data_.price) : ""
            action: qsTr("See Choice")
            onPicked: app.openUrl(shop.data_.url)
        }
        ListView {
            x: 8
            width: shop.width - 16
            height: 236
            orientation: ListView.Horizontal
            spacing: 12
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            model: shop.data_.games || []
            delegate: Tile {
                required property var modelData
                image: modelData.image
                title: modelData.title
                line1: modelData.owned ? qsTr("In your library") : modelData.worth ? qsTr("Worth %1 on its own").arg(modelData.worth) : ""
                line1Color: modelData.owned ? shop.theme.primary : shop.theme.onSurfaceVariant
                line2: ((modelData.platforms || []).indexOf("linux") !== -1 ? qsTr("Runs on Linux") + "  \u00B7  " : "")
                       + (shop.stores[modelData.store] || "")
                badge: modelData.owned ? "✓" : ""
                url: shop.data_.url
            }
        }
    }

    // --- Game bundles ----------------------------------------------------------
    Column {
        visible: shop.hasBundles
        width: shop.width
        spacing: 10
        Head {
            icon: "tag"
            title: qsTr("Game bundles")
            note: (shop.data_.bundles || []).length + ""
            action: qsTr("All bundles")
            onPicked: app.openUrl(shop.data_.bundlesUrl)
        }
        ListView {
            x: 8
            width: shop.width - 16
            height: 236
            orientation: ListView.Horizontal
            spacing: 12
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            model: shop.data_.bundles || []
            delegate: Tile {
                required property var modelData
                image: modelData.image
                title: modelData.title
                line1: (modelData.price || "")
                       + (modelData.items ? "  ·  " + qsTr("%1 items").arg(modelData.items) : "")
                line2: (modelData.when ? qsTr("Until ") + modelData.when + "  ·  " : "") + (modelData.includes || []).join(", ")
                url: modelData.url
                opensPage: false
                onPicked: bundleBox.show(modelData)
            }
        }
    }

    // A bundle's tiers against buying its games separately today (IsThereAnyDeal, with its key).
    KDialog {
        id: bundleBox
        theme: shop.theme
        property var b: ({})       // the tile: title, url, image, when
        property var d: ({})       // app.bundleReady's data
        heading: b.title || ""
        headingIcon: "tag"
        width: Math.min(parent ? parent.width - 80 : 860, 860)
        height: Math.min(parent ? parent.height - 80 : 760, 780)
        function show(bundle) { b = bundle; d = ({}); app.loadBundle(bundle.url); open() }
        Connections { target: app; function onBundleReady(url, data) { if (url === bundleBox.b.url) bundleBox.d = data } }

        contentItem: ColumnLayout {
            spacing: 12
            RowLayout {
                Layout.fillWidth: true
                spacing: 10
                Text {
                    Layout.fillWidth: true; wrapMode: Text.WordWrap
                    color: shop.theme.onSurfaceVariant; font.pixelSize: 13
                    text: bundleBox.d.url && !bundleBox.d.read ? qsTr("Humble's page for this bundle couldn't be read.")
                          : bundleBox.d.itad ? qsTr("Each tier against buying its games separately today, at the cheapest store IsThereAnyDeal knows.")
                                             : qsTr("Add a free IsThereAnyDeal API key (Settings › Library) to compare each tier with today's prices on other stores.")
                }
                KButton {
                    theme: shop.theme; primary: true; iconName: "external-link"
                    text: qsTr("Open on Humble")
                    onClicked: app.openUrl(bundleBox.b.url)
                }
            }
            Text {
                visible: !!bundleBox.d.error
                text: bundleBox.d.error || ""
                color: shop.theme.error; font.pixelSize: 12
            }
            Text {
                visible: !bundleBox.d.url
                text: qsTr("Reading the bundle…"); color: shop.theme.onSurfaceVariant; font.pixelSize: 13
            }
            ListView {
                id: tierList
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                spacing: 10
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: KScrollBar { }
                model: (bundleBox.d.tiers || []).slice().reverse()   // the whole bundle first
                delegate: Rectangle {
                    id: tierBox
                    required property var modelData
                    required property int index
                    readonly property var t: modelData
                    width: tierList.width - 12
                    implicitHeight: tierCol.implicitHeight + 24
                    radius: 12
                    color: shop.theme.surfaceContainer
                    border.width: index === 0 ? 1 : 0
                    border.color: shop.theme.primary
                    ColumnLayout {
                        id: tierCol
                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
                        spacing: 6
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 10
                            Text { text: tierBox.t.price; color: shop.theme.onSurface; font.pixelSize: 18; font.weight: Font.Bold }
                            Text { text: qsTr("%1 games").arg(tierBox.t.count) + (tierBox.index === 0 ? "  ·  " + qsTr("the whole bundle") : "")
                                   color: shop.theme.onSurfaceVariant; font.pixelSize: 13; Layout.fillWidth: true }
                        }
                        // The verdict: what the games cost separately, and the ones you don't own.
                        Text {
                            Layout.fillWidth: true; wrapMode: Text.WordWrap
                            visible: tierBox.t.separately !== ""
                            font.pixelSize: 13; font.weight: Font.DemiBold
                            color: tierBox.t.saving > 0 ? shop.theme.primary : shop.theme.error
                            text: (tierBox.t.saving > 0 ? qsTr("Separately today: %1, so the bundle saves %2%").arg(tierBox.t.separately).arg(tierBox.t.saving)
                                                        : qsTr("Separately today: %1, cheaper than the bundle").arg(tierBox.t.separately))
                                  + (tierBox.t.complete ? "" : "  " + qsTr("(%1 of %2 games have a price)").arg(tierBox.t.priced).arg(tierBox.t.count))
                        }
                        Text {
                            Layout.fillWidth: true; wrapMode: Text.WordWrap
                            visible: tierBox.t.newCount < tierBox.t.count
                            font.pixelSize: 12
                            color: shop.theme.onSurfaceVariant
                            text: tierBox.t.newCount === 0 ? qsTr("You own every game in this tier already.")
                                  : qsTr("You own %1 of them; the %2 you don't").arg(tierBox.t.count - tierBox.t.newCount).arg(tierBox.t.newCount)
                                    + (tierBox.t.separatelyNew ? qsTr(" cost %1 separately").arg(tierBox.t.separatelyNew)
                                                                 + (tierBox.t.savingNew > 0 ? qsTr(" (the bundle saves %1%)").arg(tierBox.t.savingNew)
                                                                                            : qsTr(", less than the bundle")) : "")
                        }
                        Repeater {
                            model: tierBox.t.items.filter(i => i.new)
                            RowLayout {
                                id: gameRow
                                required property var modelData
                                Layout.fillWidth: true
                                spacing: 10
                                RoundedArt {
                                    Layout.preferredWidth: 64; Layout.preferredHeight: 36; radius: 6
                                    ArtImage { anchors.fill: parent; sources: gameRow.modelData.image ? [gameRow.modelData.image] : []; sourceSize.width: 128 }
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: gameRow.modelData.title
                                    color: gameRow.modelData.owned ? shop.theme.outline : shop.theme.onSurface
                                    font.pixelSize: 13; elide: Text.ElideRight
                                }
                                Text { visible: gameRow.modelData.owned; text: "✓ " + qsTr("yours"); color: shop.theme.primary; font.pixelSize: 12 }
                                Text {
                                    text: gameRow.modelData.best.price
                                          ? gameRow.modelData.best.price + qsTr(" at ") + gameRow.modelData.best.shop
                                          : (gameRow.modelData.msrp ? qsTr("normally ") + gameRow.modelData.msrp : "")
                                    color: priceHover.hovered && gameRow.modelData.best.url ? shop.theme.primary : shop.theme.onSurfaceVariant
                                    font.pixelSize: 12
                                    HoverHandler { id: priceHover; cursorShape: gameRow.modelData.best.url ? Qt.PointingHandCursor : Qt.ArrowCursor }
                                    TapHandler { onTapped: if (gameRow.modelData.best.url) app.openUrl(gameRow.modelData.best.url) }
                                }
                            }
                        }
                        Text {
                            visible: tierBox.t.items.some(i => !i.new)
                            text: qsTr("+ everything in the tiers below")
                            color: shop.theme.outline; font.pixelSize: 12
                        }
                    }
                }
            }
        }
    }
}
