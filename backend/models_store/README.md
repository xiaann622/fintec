# Model artifacts go here

Export these from your Colab notebook (`/content/mpesa_all_models/...`) and copy
them into this folder before starting the backend. The loader in
`app/ml/pipeline.py` will auto-detect either your original notebook filenames
or the simplified names below — no code changes needed either way.

Required (pipeline will not run without these six):

| Purpose | Notebook filename you already have | Simplified alternative |
|---|---|---|
| Label model | `transaction_label_RandomForestClassifier_Label.joblib` | `transaction_label_model.joblib` |
| Label TF-IDF | `transaction_label_tfidf_vectorizer.joblib` | `transaction_label_tfidf.joblib` |
| Classification model | `transaction_classification_RandomForestClassifier_Classif.joblib` (or `LinearSVC_Classif`) | `transaction_classification_model.joblib` |
| Classification TF-IDF | `transaction_classification_tfidf_vectorizer.joblib` | `transaction_classification_tfidf.joblib` |
| Category model | `transaction_category_LogisticRegression.joblib` | `transaction_category_model.joblib` |
| Category TF-IDF | `transaction_category_tfidf_vectorizer.joblib` | `transaction_category_tfidf.joblib` |

Optional, but recommended if your models were trained on encoded integer
targets rather than raw strings (only needed if `model.predict()` returns
numbers instead of category names):

- `le_label_target.joblib` -> as `transaction_label_encoder.joblib`
- `le_classif_target.joblib` -> as `transaction_classification_encoder.joblib`
- `transaction_category_le_target.joblib` -> as `transaction_category_encoder.joblib`

Also optional — the LabelEncoders that were used as **input features** to the
downstream models (i.e. `le_label` / `le_classif` from Cell 132/142). If you
don't provide these separately, the pipeline reuses the target encoders above,
which is correct in the notebook as written (`le_label`/`le_classif` were the
same encoders as `le_label_target`/`le_classif_target`).

## Quick export snippet (run once at the end of your Colab notebook)

```python
import shutil, os
os.makedirs('/content/deploy_models', exist_ok=True)
mapping = {
    'transaction_label_RandomForestClassifier_Label.joblib': 'transaction_label_model.joblib',
    'transaction_label_tfidf_vectorizer.joblib': 'transaction_label_tfidf.joblib',
    'transaction_classification_RandomForestClassifier_Classif.joblib': 'transaction_classification_model.joblib',
    'transaction_classification_tfidf_vectorizer.joblib': 'transaction_classification_tfidf.joblib',
    'transaction_category_LogisticRegression.joblib': 'transaction_category_model.joblib',
    'transaction_category_tfidf_vectorizer.joblib': 'transaction_category_tfidf.joblib',
}
for src, dst in mapping.items():
    shutil.copy(f'/content/mpesa_all_models/{src}', f'/content/deploy_models/{dst}')
shutil.make_archive('/content/deploy_models', 'zip', '/content/deploy_models')
# Download deploy_models.zip and unzip its contents into backend/models_store/
```

After copying files here, restart the backend — check `GET /api/health` and
confirm `"models_ready": true`.
