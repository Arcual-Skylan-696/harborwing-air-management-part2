# HarborWing Air CRUD Application — IT8 Part 2

This is an independently written Streamlit application for the HarborWing Air database from the IT8 Midterm Drill. It is designed to connect to the existing MySQL schema named `mydb`; it does not create a replacement database.

## Features

- CRUD screens for the eight required entities: passengers, booking agents, reservations, payments, airports, flight schedules, flight legs, and flight costs.
- Search across loaded records in each entity browser.
- Add/remove reservation-payment links and reservation-flight-leg links. Removing a link does **not** delete the payment or leg.
- Complete reservation view with passenger, agent, payment, and flight-leg information.
- Calendar and relationship-table browsing.
- Parameterized values, input validation, transaction handling for writes, and readable error messages.
- Foreign-key constraints are allowed to block unsafe deletes.

## Requirements

- Python 3.10 or later
- MySQL Server with the Part 1 `mydb` schema and synthetic seed data already loaded

## Install

```bash
python -m venv .venv
```

Activate the environment:

- Windows: `.venv\Scripts\activate`
- macOS/Linux: `source .venv/bin/activate`

Then install dependencies:

```bash
pip install -r requirements.txt
```

## Configure the database

Set environment variables before running the app. Example for Windows Command Prompt:

```bat
set DB_HOST=localhost
set DB_PORT=3306
set DB_USER=root
set DB_PASSWORD=your_local_mysql_password
set DB_NAME=mydb
```

For PowerShell, use `$env:DB_HOST="localhost"` and equivalent commands for the other values.

Alternatively, create `.streamlit/secrets.toml` locally:

```toml
[mysql]
host = "localhost"
port = 3306
user = "root"
password = "your_local_mysql_password"
database = "mydb"
```

Do not commit `.streamlit/secrets.toml` or real credentials. `.gitignore` excludes it.

## Start

```bash
streamlit run app.py
```

The app should open in your browser. MySQL must be running, and `mydb` must already exist with the Part 1 tables and seed data.

## How an action reaches MySQL

For example, when a user creates a passenger:

1. Streamlit displays a form using the columns discovered from MySQL metadata.
2. The app validates the submitted values.
3. The app builds an `INSERT` statement using quoted table/column identifiers from database metadata and `%s` placeholders for values.
4. `mysql-connector-python` sends the query and parameter values to MySQL.
5. The app commits the transaction on success, rolls it back on failure, and shows a success or error message.

The relationship manager inserts or deletes only rows in `reservation_payment_link` or `reservation_leg_link`. It never deletes the linked payment or flight-leg record when removing a link.

## Important database safety note

The Part 1 schema script includes `DROP SCHEMA IF EXISTS mydb`. Do not rerun that script against an existing database unless you intend to delete and recreate the schema and its data. Back up your database before any reset.

## Known limitations to verify during local testing

- Search is performed over up to 1,000 rows loaded for the current table; it is not a full-database search for very large tables.
- Generic forms use database metadata, so some composite-key or domain-specific validation is ultimately enforced by MySQL. In particular, the flight number/aircraft type pair for flight costs must match `flight_schedule`.
- Reference-code values (reservation status, payment status, ticket type, travel class, airline, and aircraft type) are plain codes in the Part 1 schema rather than separate lookup tables.
- The application has no login/role-management feature because it is not specified in the Part 2 brief.

## Required demonstration checklist

1. Create a passenger.
2. Create a reservation for that passenger.
3. Add two flight legs to the reservation.
4. Create a payment and link it to the reservation.
5. View the complete reservation.
6. Update a record.
7. Remove a payment or leg link and verify the linked record still exists.
8. Safely delete an eligible record.
9. Attempt an invalid operation and show the error handling.

Test these steps using your own local `mydb` database before recording the explainer video.

## Database dependency

This application depends on the separate IT8 Midterm Drill database project. Link the GitHub URL and commit/version of your Part 1 repository here before submission:

- Midterm Drill repository: `ADD_YOUR_PART_1_REPOSITORY_URL`
- Database version/commit used: `ADD_COMMIT_HASH_OR_TAG`
