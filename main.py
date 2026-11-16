"""Start the AIT alert map web server."""

from Sulymenko import app


if __name__ == "__main__":
    app.run(debug=True, port=5001)
