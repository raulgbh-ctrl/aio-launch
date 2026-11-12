import QtQuick
import QtMultimedia

// TV mode's calm background loop (Settings > Appearance, off by default): an original piece
// made by packaging/make-ambient.py. It fades in and out instead of starting or stopping, and
// stays quiet whenever "playing" is false (a trailer, a game, the window in the background).
// Loaded through a Loader only where Qt Multimedia exists.
Item {
    id: music
    property bool playing: false
    property real level: playing ? 0.32 : 0.0
    Behavior on level { NumberAnimation { duration: 1800; easing.type: Easing.InOutQuad } }

    AudioOutput { id: out; volume: music.level }
    MediaPlayer {
        id: player
        source: Qt.resolvedUrl("../sounds/ambient.ogg")
        loops: MediaPlayer.Infinite
        audioOutput: out
    }
    // Play while it can be heard; pause once faded out (no work for a silent player).
    onLevelChanged: {
        if (level > 0 && player.playbackState !== MediaPlayer.PlayingState) player.play()
        else if (level === 0 && player.playbackState === MediaPlayer.PlayingState) player.pause()
    }
}
