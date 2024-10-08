# -*- coding: utf-8 -*-
"""GSG_Finetune_LR_batchSize.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1ufPUmao8WAvAZlX3xQa1-YhPsZS1SiSU
"""



!python --version

from google.colab import drive
drive.mount('/content/drive')

pip install datasets evaluate transformers rouge-score nltk

!apt install git-lfs

import transformers
from transformers.utils import send_example_telemetry

print(transformers.__version__)
send_example_telemetry("summarization_notebook", framework="pytorch")

model = "t5-small"

from evaluate import load
rouge_metric = load('rouge')
bleu_metric = load('bleu')

def replace_masks_with_extra_ids(text):
    """
    Replace each [MASK] token with T5 special tokens like <extra_id_0>, <extra_id_1>, etc.
    """
    mask_tokens = text.count('[MASK]')
    for i in range(mask_tokens):
        text = text.replace('[MASK]', f'<extra_id_{i}>', 1)  # Replace each [MASK] in sequence
    return text

from datasets import load_dataset, DatasetDict
import pandas as pd

data = pd.read_csv("/content/drive/My Drive/GSG.csv")  # Replace with the actual path to your CSV
data = data[['input', 'target']].head(2000)



data['input'] = data['input'].apply(replace_masks_with_extra_ids)
data['target'] = data['target'].apply(lambda x: x.strip())


print(data[['input', 'target']].head(2))

from datasets import Dataset

# Load the dataset from the CSV file
dataset = Dataset.from_pandas(data[['input', 'target']])

# Split the dataset into 80% train, 10% validation, and 10% test
split_dataset = dataset.train_test_split(test_size=0.2)
test_validation_split = split_dataset['test'].train_test_split(test_size=0.5)

# Create a DatasetDict
dataset_dict = DatasetDict({
    'train': split_dataset['train'],
    'validation': test_validation_split['train'],
    'test': test_validation_split['test']
})


# Display the DatasetDict structure
print(dataset_dict)

import numpy as np

def find_max_mean_percentile_length(column_name, percentile=90):
    lengths = [len(entry) for entry in dataset_dict['train'][column_name]]
    max_length = np.max(lengths)
    mean_length = np.mean(lengths)
    percentile_length = np.percentile(lengths, percentile)

    # Find the index where the length equals the maximum length
    max_length_index = np.where(lengths == max_length)

    print(f"Max length index in {column_name}: {max_length_index}")
    return max_length, mean_length, percentile_length

max_input_length, mean_input_length, percentile_input_length = find_max_mean_percentile_length('input')
max_target_length, mean_target_length, percentile_target_length = find_max_mean_percentile_length('target')

print('Max input AND target LENGTH:', max_input_length, max_target_length)
print('Mean input AND target LENGTH:', mean_input_length, mean_target_length)
print('90th Percentile input AND target LENGTH:', percentile_input_length, percentile_target_length)

from transformers import AutoTokenizer
tokenizer = AutoTokenizer.from_pretrained(model)

max_input_length = 256
max_target_length = 256

def preprocess_function(examples):
    # Add the prefix to the input data
    prefix = "fill in the blank: "  # You can change this prefix to any other like "complete the sentence: "

    # Add the prefix to each input example
    inputs = [prefix + doc for doc in examples["input"]]

    # Tokenize the inputs with truncation and padding
    model_inputs = tokenizer(inputs, max_length=max_input_length, truncation=True, padding="max_length")

    # Tokenize the target (label) with truncation and padding
    labels = tokenizer(text_target=examples["target"], max_length=max_target_length, truncation=True, padding="max_length")

    # Assign tokenized labels to model_inputs
    model_inputs["labels"] = labels["input_ids"]

    return model_inputs

tokenized_datasets = dataset_dict.map(preprocess_function, batched=True)

from transformers import AutoModelForSeq2SeqLM, DataCollatorForSeq2Seq, Seq2SeqTrainingArguments, Seq2SeqTrainer

model_T5 = AutoModelForSeq2SeqLM.from_pretrained(model)

from transformers import TrainerCallback
import pandas as pd
import os



class PrintMetricsCallback(TrainerCallback):
    def __init__(self,saved_path,model_saved_path,batch_size,lr, model, tokenizer):
        self.count=0
        self.each_epoch_log_dict={}
        self.saved_path=saved_path
        self.model_saved_path=model_saved_path
        self.model = model
        self.tokenizer = tokenizer
        self.batch_size=batch_size
        self.lr=lr

    def on_log(self, args, state, control, logs=None, **kwargs):
        # Logs is a dictionary with metric names as keys
        if logs is not None:
            self.count +=1
            print(self.count)
            # Print each metric including loss
            print("Metrics at epoch end:")
            for key, value in logs.items():
                self.each_epoch_log_dict[key]=value

            if self.count%2==0:

                try:
                  os.makedirs(self.saved_path, exist_ok=True)
                except Exception as e:
                  print(f"Error creating directory {self.saved_path}: {e}")
                # Create the file path for the CSV
                csv_file = os.path.join(self.saved_path, f'batch_size_{self.batch_size}.csv')


                if os.path.exists(csv_file):
                    # Load the existing CSV file into a DataFrame
                    df = pd.read_csv(csv_file)
                    # Convert the dictionary to a DataFrame
                    new_df = pd.DataFrame([self.each_epoch_log_dict])
                    new_df.insert(0, 'Batch Size', self.batch_size)
                    new_df.insert(1, 'Learning Rate', self.lr)
                    # Append the new DataFrame to the existing DataFrame
                    df = pd.concat([df,new_df], ignore_index=True)
                else:
                    # If the file does not exist, create a new DataFrame with the new data
                    df = pd.DataFrame([self.each_epoch_log_dict])
                    df.insert(0, 'Batch Size', self.batch_size)
                    df.insert(1, 'Learning Rate', self.lr)


                df.to_csv(csv_file, index=False)
                print(f'New data has been added to {csv_file}.')

    def on_epoch_end(self, args, state, control, **kwargs):
            # Get the optimizer from kwargs if available
            optimizer = kwargs['optimizer']

            try:
                os.makedirs(self.model_saved_path, exist_ok=True)
            except Exception as e:
                print(f"Error creating directory {self.model_saved_path}: {e}")
                return

            # Save model and tokenizer with learning rate in the filename
            try:
                self.model.save_pretrained(self.model_saved_path)
                self.tokenizer.save_pretrained(self.model_saved_path)
                print(f"Model and tokenizer saved to {self.model_saved_path}")
            except Exception as e:
                print(f"Error saving model to {self.model_saved_path}: {e}")

import nltk
import numpy as np

nltk.download('punkt')

def compute_metrics(eval_pred):
    predictions, labels = eval_pred
    decoded_preds = tokenizer.batch_decode(predictions, skip_special_tokens=True)

    # Replace -100 in the labels as we can't decode them.
    labels = np.where(labels != -100, labels, tokenizer.pad_token_id)
    decoded_labels = tokenizer.batch_decode(labels, skip_special_tokens=True)

    # Rouge expects a newline after each sentence
    decoded_preds = ["\n".join(nltk.sent_tokenize(pred.strip())) for pred in decoded_preds]
    decoded_labels = ["\n".join(nltk.sent_tokenize(label.strip())) for label in decoded_labels]

    # Ensure that predictions and labels are aligned and non-empty
    aligned_preds, aligned_labels = [], []
    for pred, label in zip(decoded_preds, decoded_labels):
        if len(pred.strip()) > 0:  # Only add non-empty predictions
            aligned_preds.append(pred)
            aligned_labels.append(label)
    print(len(aligned_preds))
    print(len(aligned_labels))
    # If no valid predictions or labels, return 0 to avoid errors
    if len(aligned_preds) == 0 or len(aligned_labels) == 0:
        return {
            "bleu": 0.0,
            "rouge1": 0.0,
            "rouge2": 0.0,
            "rougeL": 0.0,
            "gen_len": 0.0
        }

    # Compute ROUGE scores
    rouge_result = rouge_metric.compute(predictions=aligned_preds, references=aligned_labels, use_stemmer=True)
    rouge_result = {key: value * 100 for key, value in rouge_result.items()}  # Convert to percentage

    # BLEU expects tokenized sequences, so let's keep the sentences as strings
    aligned_preds_word = [pred.strip() for pred in aligned_preds]  # Keep them as strings
    aligned_labels_word = [[label.strip()] for label in aligned_labels]  # Keep them as lists of strings

    # Compute BLEU score
    bleu_result = bleu_metric.compute(predictions=aligned_preds_word, references=aligned_labels_word)
    bleu_scores = {
        "bleu": bleu_result['bleu'] * 100,  # Cumulative BLEU score
        "bleu1": bleu_result['precisions'][0] * 100,  # BLEU-1 score
        "bleu2": bleu_result['precisions'][1] * 100,  # BLEU-2 score
        "bleu3": bleu_result['precisions'][2] * 100,  # BLEU-3 score
        "bleu4": bleu_result['precisions'][3] * 100,  # BLEU-4 score
    }

    # Add mean generated length
    prediction_lens = [np.count_nonzero(pred != tokenizer.pad_token_id) for pred in predictions]
    result = {
        **rouge_result,
        **bleu_scores,
        "gen_len": np.mean(prediction_lens)
    }

    return {k: round(v, 4) for k, v in result.items()}

from huggingface_hub import notebook_login

notebook_login()

batch_sizes = [8,16,32]
learning_rates = [0.001, 0.003, 0.005, 0.007, 0.009]

for batch_size in batch_sizes:

    print(f"Training with batch size: {batch_size}")
    csv_saved_path= f'/content/drive/My Drive/Summerization/GSG_FINETUNE/LOG'

    for lr in learning_rates:

        model_saved_path= f'/content/drive/My Drive/Summerization/GSG_FINETUNE/MODEL_EPOCH/model_batch_size_{batch_size}_lr_{lr}'
        print(f"Training with learning rate: {lr}")

        model_T5 = AutoModelForSeq2SeqLM.from_pretrained(model)
        print_metrics_callback = PrintMetricsCallback(csv_saved_path,model_saved_path,batch_size,lr, model=model_T5, tokenizer=tokenizer)


        args = Seq2SeqTrainingArguments(
                f"t5-small-finetuned-X-Ray_T5-lr-{lr }",
                evaluation_strategy="epoch",
                logging_strategy="epoch",  # Log at specific intervals to capture training loss
                learning_rate=lr,
                per_device_train_batch_size=batch_size,
                per_device_eval_batch_size=batch_size ,
                weight_decay=0.01,
                save_total_limit=3,
                num_train_epochs=1,
                predict_with_generate=True,
                fp16=True,
                push_to_hub=False,
        )

        data_collator = DataCollatorForSeq2Seq(tokenizer, model=model_T5)



        trainer = Seq2SeqTrainer(
                model=model_T5,
                args=args,
                train_dataset=tokenized_datasets["train"],
                eval_dataset=tokenized_datasets["validation"],
                data_collator=data_collator,
                tokenizer=tokenizer,
                compute_metrics=compute_metrics,
                callbacks=[ print_metrics_callback]
        )

        train_result = trainer.train()