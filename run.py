from app import create_app, db

app = create_app()

if __name__ == '__main__':
    with app.app_context():
        # This is the "Magic" line. Importing them here registers them 
        # inside the application context so db.create_all() sees them.
        from app.models import User, Lecture, Quiz, ClassSession
        
        try:
            db.create_all()
            print("--- Database Tables Synchronized! ---")
        except Exception as e:
            print(f"--- Database Error: {e} ---")

    app.run(debug=True)