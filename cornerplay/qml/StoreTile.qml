import QtQuick

// A store's logo in white on a soft rounded tile of the store's colour.
Rectangle {
    id: st
    property string store: ""
    property int size: 22
    width: size; height: size
    radius: Math.round(size * 0.28)
    color: (app.storesInfo.find(s => s.id === st.store) || {}).tile || "#5f646b"
    StoreIcon { anchors.centerIn: parent; size: Math.round(st.size * 0.62); store: st.store; color: "white" }
}
