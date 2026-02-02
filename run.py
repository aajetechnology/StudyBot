from app import create_app, db

app = create_app()

if __name__ == '__main__':
    # This block ensures tables are created before the server starts
    with app.app_context():
        db.create_all()
        print("✅ Database tables verified/created.")

    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)