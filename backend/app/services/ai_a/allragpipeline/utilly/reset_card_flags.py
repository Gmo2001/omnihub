from google.cloud import firestore
db = firestore.Client(project="jnu-rise-edu-147")
docs = db.collection("profiles").stream()

for doc in docs:
    doc.reference.update({"process_flags.card": True})
    print(f"Reset flag for {doc.id}")