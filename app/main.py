from __future__ import annotations

from app.db import connect, init_db
from app.gui import RecyclingPOSApp
from app.seed_data import seed_materials


def main() -> None:
    conn = connect()
    init_db(conn)
    seed_materials(conn)
    app = RecyclingPOSApp(conn)
    app.mainloop()


if __name__ == "__main__":
    main()

