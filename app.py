import os
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import mysql.connector
import streamlit as st
from mysql.connector import Error

st.set_page_config(
    page_title="HarborWing Air | CRUD",
    page_icon="✈️",
    layout="wide",
)

CORE_TABLES = {
    "Passengers": "passenger",
    "Booking agents": "booking_agent",
    "Reservations": "reservation",
    "Payments": "payment",
    "Airports": "airport",
    "Flight schedules": "flight_schedule",
    "Flight legs": "flight_leg",
    "Flight costs": "flight_cost",
}
REFERENCE_TABLES = [
    "calendar_date",
    "reservation_payment_link",
    "reservation_leg_link",
]


def db_config():
    """Read connection settings from environment variables or Streamlit secrets."""
    try:
        secrets = st.secrets.get("mysql", {})
    except Exception:
        # Streamlit may raise an exception if secrets.toml is missing or invalid.
        secrets = {}

    return {
        "host": os.getenv("DB_HOST") or secrets.get("host", "localhost"),
        "port": int(os.getenv("DB_PORT") or secrets.get("port", 3306)),
        "user": os.getenv("DB_USER") or secrets.get("user", "root"),
        # A blank password is valid for some local XAMPP installations.
        "password": os.getenv("DB_PASSWORD")
        if os.getenv("DB_PASSWORD") is not None
        else secrets.get("password", ""),
        "database": os.getenv("DB_NAME") or secrets.get("database", "mydb"),
        "connection_timeout": 5,
    }


def connect_db():
    """Connect to MySQL. Do not reject a blank password automatically."""
    cfg = db_config()
    return mysql.connector.connect(**cfg)


def qi(name):
    """Safely quote an SQL identifier obtained from database metadata."""
    return "`" + str(name).replace("`", "``") + "`"


def get_tables(conn):
    cur = conn.cursor()
    try:
        cur.execute("SHOW FULL TABLES WHERE Table_type = 'BASE TABLE'")
        return [row[0] for row in cur.fetchall()]
    finally:
        cur.close()


def get_columns(conn, table):
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(f"SHOW FULL COLUMNS FROM {qi(table)}")
        return cur.fetchall()
    finally:
        cur.close()


def get_primary_keys(conn, table):
    cur = conn.cursor()
    try:
        cur.execute(f"SHOW KEYS FROM {qi(table)} WHERE Key_name = 'PRIMARY'")
        rows = cur.fetchall()
        return [row[4] for row in sorted(rows, key=lambda row: row[3])]
    finally:
        cur.close()


def get_foreign_keys(conn, table):
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(
            """
            SELECT COLUMN_NAME, REFERENCED_TABLE_NAME,
                   REFERENCED_COLUMN_NAME, CONSTRAINT_NAME, ORDINAL_POSITION
            FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
              AND REFERENCED_TABLE_NAME IS NOT NULL
            ORDER BY CONSTRAINT_NAME, ORDINAL_POSITION
            """,
            (table,),
        )
        return cur.fetchall()
    finally:
        cur.close()


def get_rows(conn, table, limit=500):
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(f"SELECT * FROM {qi(table)} LIMIT %s", (limit,))
        return cur.fetchall()
    finally:
        cur.close()


def table_columns(conn, table):
    return [column["Field"] for column in get_columns(conn, table)]


def get_fk_options(conn, ref_table, ref_column):
    cur = conn.cursor()
    try:
        cur.execute(
            f"SELECT {qi(ref_column)} FROM {qi(ref_table)} "
            f"ORDER BY {qi(ref_column)} LIMIT 1000"
        )
        return [row[0] for row in cur.fetchall()]
    finally:
        cur.close()


def value_label(value):
    return "— Select —" if value is None else str(value)


def render_field(
    conn, table, col, current=None, key_prefix="field", disabled=False
):
    name = col["Field"]
    sql_type = str(col.get("Type", "")).lower()
    nullable = col.get("Null") == "YES"
    extra = str(col.get("Extra", "")).lower()
    default = col.get("Default")

    if "auto_increment" in extra:
        return None

    foreign_keys = [
        fk for fk in get_foreign_keys(conn, table)
        if fk["COLUMN_NAME"] == name
    ]

    if foreign_keys:
        fk = foreign_keys[0]
        options = get_fk_options(
            conn,
            fk["REFERENCED_TABLE_NAME"],
            fk["REFERENCED_COLUMN_NAME"],
        )
        choices = ([None] if nullable else []) + options
        if not choices:
            st.warning(
                f"No available values for {name}. Create its referenced "
                f"record first in {fk['REFERENCED_TABLE_NAME']}."
            )
            return None

        if current not in choices:
            current = None if nullable else options[0]
        labels = {value: value_label(value) for value in choices}
        index = choices.index(current) if current in choices else 0

        return st.selectbox(
            name,
            choices,
            index=index,
            format_func=lambda value: labels.get(value, str(value)),
            key=f"{key_prefix}_{table}_{name}",
            disabled=disabled,
            help=(
                f"References {fk['REFERENCED_TABLE_NAME']}."
                f"{fk['REFERENCED_COLUMN_NAME']}"
            ),
        )

    if "datetime" in sql_type or "timestamp" in sql_type:
        initial = (
            current
            if isinstance(current, datetime)
            else datetime.now().replace(microsecond=0)
        )
        chosen_date = st.date_input(
            name + " — date",
            value=initial.date(),
            key=f"{key_prefix}_{table}_{name}_date",
            disabled=disabled,
        )
        chosen_time = st.time_input(
            name + " — time",
            value=initial.time().replace(microsecond=0),
            key=f"{key_prefix}_{table}_{name}_time",
            disabled=disabled,
        )
        return datetime.combine(chosen_date, chosen_time)

    if sql_type == "date":
        initial = current if isinstance(current, date) else date.today()
        return st.date_input(
            name,
            value=initial,
            key=f"{key_prefix}_{table}_{name}",
            disabled=disabled,
        )

    if any(
        kind in sql_type
        for kind in ("int", "decimal", "numeric", "float", "double")
    ):
        if any(kind in sql_type for kind in ("decimal", "numeric", "float", "double")):
            try:
                value = float(current if current is not None else (default or 0))
            except (TypeError, ValueError):
                value = 0.0
            return st.number_input(
                name,
                value=value,
                key=f"{key_prefix}_{table}_{name}",
                disabled=disabled,
            )

        try:
            value = int(current if current is not None else (default or 0))
        except (TypeError, ValueError):
            value = 0
        return st.number_input(
            name,
            value=value,
            step=1,
            key=f"{key_prefix}_{table}_{name}",
            disabled=disabled,
        )

    if "text" in sql_type:
        value = "" if current is None else str(current)
        result = st.text_area(
            name + (" (optional)" if nullable else ""),
            value=value,
            key=f"{key_prefix}_{table}_{name}",
            disabled=disabled,
        )
        return result if result != "" or not nullable else None

    value = "" if current is None else str(current)
    result = st.text_input(
        name + (" (optional)" if nullable else ""),
        value=value,
        key=f"{key_prefix}_{table}_{name}",
        disabled=disabled,
    )
    return result if result != "" or not nullable else None


def normalize_value(col, value):
    if value == "" and col.get("Null") == "YES":
        return None

    sql_type = str(col.get("Type", "")).lower()
    if value is None:
        return None

    if "decimal" in sql_type or "numeric" in sql_type:
        try:
            return Decimal(str(value)).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            raise ValueError(f"{col['Field']} must be a valid number.")

    if "int" in sql_type:
        return int(value)

    return value


def validate_record(table, record):
    if table == "reservation":
        if int(record.get("party_size") or 0) <= 0:
            raise ValueError("Party size must be greater than zero.")

    if table == "payment":
        if Decimal(str(record.get("payment_amount") or 0)) <= 0:
            raise ValueError("Payment amount must be greater than zero.")

    if table == "flight_cost":
        amount = Decimal(str(record.get("cost_amount") or 0))
        if amount < 0:
            raise ValueError("Flight cost cannot be negative.")

        valid_from = record.get("valid_from_date")
        valid_to = record.get("valid_to_date")
        if valid_from is not None and valid_to is not None and valid_to < valid_from:
            raise ValueError(
                "Valid-to date cannot be earlier than valid-from date."
            )

    if table in ("flight_schedule", "flight_leg"):
        if (
            record.get("origin_airport_code")
            == record.get("destination_airport_code")
        ):
            raise ValueError("Origin and destination airports must be different.")

    if table == "flight_schedule":
        departure = record.get("scheduled_departure_datetime")
        arrival = record.get("scheduled_arrival_datetime")
        if departure is not None and arrival is not None and arrival <= departure:
            raise ValueError(
                "Scheduled arrival must be later than scheduled departure."
            )

    if table == "flight_leg":
        departure = record.get("actual_departure_datetime")
        arrival = record.get("actual_arrival_datetime")
        if departure is not None and arrival is not None and arrival <= departure:
            raise ValueError(
                "Actual arrival must be later than actual departure."
            )


def check_flight_cost_pair(conn, record):
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT 1
            FROM flight_schedule
            WHERE flight_number = %s AND aircraft_type_code = %s
            LIMIT 1
            """,
            (record.get("flight_number"), record.get("aircraft_type_code")),
        )
        if cur.fetchone() is None:
            raise ValueError(
                "The selected flight number and aircraft type must match "
                "a row in flight_schedule."
            )
    finally:
        cur.close()


def execute_write(conn, sql, values):
    cur = conn.cursor()
    try:
        cur.execute(sql, values)
        conn.commit()
        return cur.rowcount
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def show_entity_manager(conn, title, table):
    st.subheader(title)
    columns = get_columns(conn, table)
    primary_keys = get_primary_keys(conn, table)
    rows = get_rows(conn, table, 1000)

    if not primary_keys:
        st.error(f"The table '{table}' does not have a primary key.")
        return

    if not rows:
        st.info("No records found in this table yet.")
    else:
        search = st.text_input(
            "Search visible records",
            key=f"search_{table}",
            placeholder="Type a value to filter...",
        )
        filtered = rows
        if search:
            term = search.casefold()
            filtered = [
                row for row in rows
                if any(
                    term in str(value).casefold()
                    for value in row.values()
                    if value is not None
                )
            ]
        st.caption(
            f"Showing {len(filtered)} of up to {len(rows)} loaded records "
            "(maximum 1,000)."
        )
        st.dataframe(filtered, use_container_width=True, hide_index=True)

    create_tab, update_tab, delete_tab = st.tabs(["Create", "Update", "Delete"])

    with create_tab:
        st.markdown("**Create a new record**")
        with st.form(f"create_form_{table}"):
            values = {}
            for col in columns:
                value = render_field(conn, table, col, key_prefix="create")
                if "auto_increment" not in str(col.get("Extra", "")).lower():
                    if value is not None or col.get("Null") == "YES":
                        values[col["Field"]] = value
            submitted = st.form_submit_button("Create record", type="primary")

        if submitted:
            try:
                record = {
                    key: normalize_value(
                        next(col for col in columns if col["Field"] == key),
                        value,
                    )
                    for key, value in values.items()
                }
                validate_record(table, record)
                if table == "flight_cost":
                    check_flight_cost_pair(conn, record)

                fields = list(record)
                if not fields:
                    raise ValueError("There are no fields to insert.")

                sql = (
                    f"INSERT INTO {qi(table)} "
                    f"({', '.join(qi(field) for field in fields)}) "
                    f"VALUES ({', '.join(['%s'] * len(fields))})"
                )
                execute_write(conn, sql, tuple(record[field] for field in fields))
                st.success("Record created successfully.")
                st.rerun()
            except Exception as exc:
                st.error(f"Could not create record: {exc}")

    rows = get_rows(conn, table, 1000)

    with update_tab:
        if not rows:
            st.info("There are no records to update.")
        else:
            selected = st.selectbox(
                "Select record to update",
                rows,
                format_func=lambda row: " | ".join(
                    f"{key}={row[key]}" for key in primary_keys
                ),
                key=f"update_select_{table}",
            )
            with st.form(f"update_form_{table}"):
                values = {}
                for col in columns:
                    name = col["Field"]
                    if name in primary_keys:
                        st.text_input(
                            name + " (primary key)",
                            value=str(selected[name]),
                            disabled=True,
                            key=f"update_pk_{table}_{name}",
                        )
                        continue
                    values[name] = render_field(
                        conn,
                        table,
                        col,
                        current=selected.get(name),
                        key_prefix="update",
                    )
                submitted = st.form_submit_button("Save changes", type="primary")

            if submitted:
                try:
                    record = {
                        key: normalize_value(
                            next(col for col in columns if col["Field"] == key),
                            value,
                        )
                        for key, value in values.items()
                    }
                    record.update({key: selected[key] for key in primary_keys})
                    validate_record(table, record)
                    if table == "flight_cost":
                        check_flight_cost_pair(conn, record)

                    fields = list(values)
                    if not fields:
                        raise ValueError("There are no editable fields.")

                    where = " AND ".join(
                        f"{qi(key)} = %s" for key in primary_keys
                    )
                    sql = (
                        f"UPDATE {qi(table)} SET "
                        + ", ".join(f"{qi(key)} = %s" for key in fields)
                        + f" WHERE {where}"
                    )
                    count = execute_write(
                        conn,
                        sql,
                        tuple(record[key] for key in fields)
                        + tuple(selected[key] for key in primary_keys),
                    )
                    if count == 0:
                        st.warning(
                            "No changes were made, or the record no longer exists."
                        )
                    else:
                        st.success("Record updated successfully.")
                        st.rerun()
                except Exception as exc:
                    st.error(f"Could not update record: {exc}")

    with delete_tab:
        if not rows:
            st.info("There are no records to delete.")
        else:
            selected = st.selectbox(
                "Select record to delete",
                rows,
                format_func=lambda row: " | ".join(
                    f"{key}={row[key]}" for key in primary_keys
                ),
                key=f"delete_select_{table}",
            )
            st.warning(
                "Deletion may be blocked if another record references this "
                "record. Related data is protected by database constraints."
            )
            confirm = st.checkbox(
                "I understand and want to attempt this deletion.",
                key=f"confirm_delete_{table}",
            )
            if st.button(
                "Delete selected record",
                key=f"delete_btn_{table}",
                disabled=not confirm,
            ):
                try:
                    where = " AND ".join(
                        f"{qi(key)} = %s" for key in primary_keys
                    )
                    count = execute_write(
                        conn,
                        f"DELETE FROM {qi(table)} WHERE {where}",
                        tuple(selected[key] for key in primary_keys),
                    )
                    if count:
                        st.success("Record deleted successfully.")
                        st.rerun()
                    else:
                        st.warning(
                            "No record was deleted; it may no longer exist."
                        )
                except Exception as exc:
                    st.error(f"Deletion was blocked or failed: {exc}")


def show_relationship_manager(conn):
    st.subheader("Reservation relationship manager")
    reservations = get_rows(conn, "reservation", 1000)
    if not reservations:
        st.info("Create a reservation before managing links.")
        return

    reservation = st.selectbox(
        "Reservation",
        reservations,
        format_func=lambda row: (
            f"{row.get('reservation_code', 'Reservation')} "
            f"(ID {row['reservation_id']})"
        ),
        key="link_reservation",
    )
    reservation_id = reservation["reservation_id"]
    payment_tab, leg_tab = st.tabs(["Payments", "Flight legs"])

    with payment_tab:
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute(
                """
                SELECT p.*
                FROM payment p
                JOIN reservation_payment_link l ON l.payment_id = p.payment_id
                WHERE l.reservation_id = %s
                ORDER BY p.payment_id
                """,
                (reservation_id,),
            )
            linked_payments = cur.fetchall()
        finally:
            cur.close()

        st.write("Currently linked payments")
        st.dataframe(linked_payments, use_container_width=True, hide_index=True)

        all_payments = get_rows(conn, "payment", 1000)
        linked_ids = {row["payment_id"] for row in linked_payments}
        available = [
            row for row in all_payments
            if row["payment_id"] not in linked_ids
        ]

        if available:
            chosen = st.selectbox(
                "Payment to link",
                available,
                format_func=lambda row: (
                    f"ID {row['payment_id']} — {row['payment_amount']} "
                    f"({row['payment_status_code']})"
                ),
                key="payment_to_link",
            )
            if st.button("Add payment link"):
                try:
                    execute_write(
                        conn,
                        """
                        INSERT INTO reservation_payment_link
                            (reservation_id, payment_id)
                        VALUES (%s, %s)
                        """,
                        (reservation_id, chosen["payment_id"]),
                    )
                    st.success(
                        "Payment link added. The payment record itself was not changed."
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(f"Could not add payment link: {exc}")
        else:
            st.caption("No unlinked payments available.")

        if linked_payments:
            remove_payment = st.selectbox(
                "Payment link to remove",
                linked_payments,
                format_func=lambda row: (
                    f"ID {row['payment_id']} — {row['payment_amount']}"
                ),
                key="payment_to_unlink",
            )
            if st.button("Remove payment link"):
                try:
                    execute_write(
                        conn,
                        """
                        DELETE FROM reservation_payment_link
                        WHERE reservation_id = %s AND payment_id = %s
                        """,
                        (reservation_id, remove_payment["payment_id"]),
                    )
                    st.success(
                        "Payment link removed. The payment record was preserved."
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(f"Could not remove payment link: {exc}")

    with leg_tab:
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute(
                """
                SELECT fl.*
                FROM flight_leg fl
                JOIN reservation_leg_link l ON l.leg_id = fl.leg_id
                WHERE l.reservation_id = %s
                ORDER BY fl.leg_id
                """,
                (reservation_id,),
            )
            linked_legs = cur.fetchall()
        finally:
            cur.close()

        st.write("Currently linked flight legs")
        st.dataframe(linked_legs, use_container_width=True, hide_index=True)

        all_legs = get_rows(conn, "flight_leg", 1000)
        linked_ids = {row["leg_id"] for row in linked_legs}
        available = [row for row in all_legs if row["leg_id"] not in linked_ids]

        if available:
            chosen = st.selectbox(
                "Flight leg to link",
                available,
                format_func=lambda row: (
                    f"Leg {row['leg_id']} — {row['flight_number']} "
                    f"{row['origin_airport_code']} → "
                    f"{row['destination_airport_code']}"
                ),
                key="leg_to_link",
            )
            if st.button("Add flight-leg link"):
                try:
                    execute_write(
                        conn,
                        """
                        INSERT INTO reservation_leg_link (reservation_id, leg_id)
                        VALUES (%s, %s)
                        """,
                        (reservation_id, chosen["leg_id"]),
                    )
                    st.success(
                        "Flight-leg link added. The flight leg itself was not changed."
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(f"Could not add flight-leg link: {exc}")
        else:
            st.caption("No unlinked flight legs available.")

        if linked_legs:
            remove_leg = st.selectbox(
                "Flight-leg link to remove",
                linked_legs,
                format_func=lambda row: (
                    f"Leg {row['leg_id']} — {row['flight_number']}"
                ),
                key="leg_to_unlink",
            )
            if st.button("Remove flight-leg link"):
                try:
                    execute_write(
                        conn,
                        """
                        DELETE FROM reservation_leg_link
                        WHERE reservation_id = %s AND leg_id = %s
                        """,
                        (reservation_id, remove_leg["leg_id"]),
                    )
                    st.success(
                        "Flight-leg link removed. The flight-leg record was preserved."
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(f"Could not remove flight-leg link: {exc}")


def show_reservation_details(conn):
    st.subheader("Complete reservation view")
    reservations = get_rows(conn, "reservation", 1000)
    if not reservations:
        st.info("No reservations are available.")
        return

    selected = st.selectbox(
        "Choose reservation",
        reservations,
        format_func=lambda row: (
            f"{row.get('reservation_code', 'Reservation')} "
            f"(ID {row['reservation_id']})"
        ),
        key="details_reservation",
    )
    reservation_id = selected["reservation_id"]

    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(
            """
            SELECT r.*, p.first_name, p.second_name, p.last_name,
                   p.email_address, a.agent_name
            FROM reservation r
            JOIN passenger p ON p.passenger_id = r.passenger_id
            LEFT JOIN booking_agent a ON a.agent_id = r.agent_id
            WHERE r.reservation_id = %s
            """,
            (reservation_id,),
        )
        header = cur.fetchone()
    finally:
        cur.close()

    st.markdown("**Reservation and passenger**")
    st.dataframe([header] if header else [], use_container_width=True, hide_index=True)

    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(
            """
            SELECT p.payment_id, p.payment_status_code,
                   p.payment_date, p.payment_amount
            FROM payment p
            JOIN reservation_payment_link l ON l.payment_id = p.payment_id
            WHERE l.reservation_id = %s
            ORDER BY p.payment_id
            """,
            (reservation_id,),
        )
        payments = cur.fetchall()
    finally:
        cur.close()

    st.markdown("**Linked payments**")
    st.dataframe(payments, use_container_width=True, hide_index=True)

    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(
            """
            SELECT fl.leg_id, fl.flight_number, fl.origin_airport_code,
                   fl.destination_airport_code, fl.actual_departure_datetime,
                   fl.actual_arrival_datetime
            FROM flight_leg fl
            JOIN reservation_leg_link l ON l.leg_id = fl.leg_id
            WHERE l.reservation_id = %s
            ORDER BY fl.actual_departure_datetime
            """,
            (reservation_id,),
        )
        legs = cur.fetchall()
    finally:
        cur.close()

    st.markdown("**Linked flight legs**")
    st.dataframe(legs, use_container_width=True, hide_index=True)


def show_reference_records(conn):
    st.subheader("Calendar and supporting reference records")
    st.caption(
        "The Midterm schema uses code values such as ticket type, travel class, "
        "status, airline, and aircraft type without separate lookup tables. "
        "Calendar dates are maintained by the Midterm seed script."
    )
    available = [table for table in REFERENCE_TABLES if table in get_tables(conn)]
    choices = available or ["calendar_date"]
    chosen = st.selectbox(
        "Reference table",
        choices,
        key="reference_table",
    )
    if chosen not in get_tables(conn):
        st.warning(
            f"The table '{chosen}' does not exist in the selected database. "
            "Import the Part 1 schema and seed data first."
        )
        return
    st.dataframe(get_rows(conn, chosen, 1000), use_container_width=True, hide_index=True)


st.title("✈️ HarborWing Air Management")
st.caption(
    "Part 2 CRUD application — connected to the MySQL database from the Midterm Drill."
)

conn = None
try:
    conn = connect_db()
except Exception as exc:
    st.error("Could not connect to the Midterm database.")
    st.info(
        "Check that XAMPP MySQL is running and that the host, port, username, "
        "password, and database name match your local MySQL setup. "
        "The expected database name is `mydb`."
    )
    with st.expander("Connection details"):
        st.code(str(exc))
    st.stop()

try:
    actual_tables = set(get_tables(conn))
    missing = set(CORE_TABLES.values()) - actual_tables

    if missing:
        st.error(
            "The selected database is missing expected Part 1 tables: "
            + ", ".join(sorted(missing))
        )
        st.info(
            "Check that DB_NAME is set to `mydb` and that the Part 1 schema "
            "has been imported into that database."
        )
        st.stop()

    tabs = st.tabs(
        [
            "Dashboard",
            "CRUD",
            "Reservation details",
            "Relationship links",
            "Calendar & references",
        ]
    )

    with tabs[0]:
        st.subheader("Database overview")
        st.success("Connected to the configured MySQL database.")
        metric_columns = st.columns(4)
        for index, (label, table) in enumerate(CORE_TABLES.items()):
            cur = conn.cursor()
            try:
                cur.execute(f"SELECT COUNT(*) FROM {qi(table)}")
                count = cur.fetchone()[0]
            finally:
                cur.close()
            metric_columns[index % 4].metric(label, count)

        st.markdown("**Required entities**")
        st.write(
            "Use the CRUD tab to create, read, update, and delete records "
            "in the eight required entities."
        )
        st.caption(
            "For referenced records, deletion is safely rejected by MySQL "
            "foreign-key constraints and the application displays the error."
        )

    with tabs[1]:
        selected_label = st.selectbox(
            "Entity",
            list(CORE_TABLES.keys()),
            key="entity_select",
        )
        show_entity_manager(conn, selected_label, CORE_TABLES[selected_label])

    with tabs[2]:
        show_reservation_details(conn)

    with tabs[3]:
        show_relationship_manager(conn)

    with tabs[4]:
        show_reference_records(conn)

except Error as exc:
    st.error(f"MySQL database error: {exc}")
except Exception as exc:
    st.error(f"Application error: {exc}")
finally:
    if conn is not None and conn.is_connected():
        conn.close()
