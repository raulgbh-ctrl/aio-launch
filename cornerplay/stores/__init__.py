

def all_stores():
    """One of every store, in the order the app lists them. The one list of stores: the app,
    `--status` and `--play` (what Steam shortcuts run) all take it from here."""
    from .amazon import Amazon
    from .battlenet import BattleNet
    from .custom import Custom
    from .epic import Epic
    from .gog import Gog
    from .humble import Humble
    from .itch import Itch
    from .retro import Retro
    from .steam import Steam
    return [Steam(), Epic(), Gog(), Amazon(), BattleNet(), Humble(), Itch(), Retro(), Custom()]
