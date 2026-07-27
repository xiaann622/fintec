import joblib

v = joblib.load("models_store/transaction_label_tfidf_vectorizer.joblib")

print(type(v))
print("idf:", hasattr(v, "idf_"))
print("vocab:", hasattr(v, "vocabulary_"))

if hasattr(v, "idf_"):
    print("idf length:", len(v.idf_))

if hasattr(v, "vocabulary_"):
    print("vocab length:", len(v.vocabulary_))