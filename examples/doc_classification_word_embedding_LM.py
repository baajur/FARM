# fmt: off
import logging
from pathlib import Path
import time

from farm.data_handler.data_silo import DataSilo, StreamingDataSilo
from farm.data_handler.processor import TextClassificationProcessor
from farm.modeling.optimization import initialize_optimizer
from farm.infer import Inferencer
from farm.modeling.adaptive_model import AdaptiveModel
from farm.modeling.language_model import LanguageModel
from farm.modeling.prediction_head import TextClassificationHead
from farm.modeling.tokenization import Tokenizer
from farm.train import Trainer
from farm.utils import set_all_seeds, MLFlowLogger, initialize_device_settings

def doc_classifcation():
    logging.basicConfig(
        format="%(asctime)s - %(levelname)s - %(name)s -   %(message)s",
        datefmt="%m/%d/%Y %H:%M:%S",
        level=logging.INFO)

    ml_logger = MLFlowLogger(tracking_uri="https://public-mlflow.deepset.ai/")
    ml_logger.init_experiment(experiment_name="Public_FARM", run_name="Run_doc_classification_glove")

    ##########################
    ########## Settings
    ##########################
    set_all_seeds(seed=42)
    n_epochs = 3
    batch_size = 32
    evaluate_every = 100
    # load from a local path:
    lang_model = Path("../saved_models/glove-german-uncased")
    # or through s3
    #lang_model = "glove-german-uncased"
    do_lower_case = True

    device, n_gpu = initialize_device_settings(use_cuda=True)

    # 1.Create a tokenizer
    tokenizer = Tokenizer.load(pretrained_model_name_or_path=lang_model, do_lower_case=do_lower_case)

    # 2. Create a DataProcessor that handles all the conversion from raw text into a pytorch Dataset
    # Here we load GermEval 2018 Data.
    label_list = ["OTHER", "OFFENSE"]
    metric = "f1_macro"

    processor = TextClassificationProcessor(
        tokenizer=tokenizer,
        max_seq_len=128,
        data_dir=Path("../data/germeval18"),
        label_list=label_list,
        dev_split=0,
        test_filename="test.tsv",
        train_filename="train.tsv",
        metric=metric,
        label_column_name="coarse_label")


    # 3. Create a DataSilo that loads several datasets (train/dev/test), provides DataLoaders for them and calculates a
    data_silo = DataSilo(
        processor=processor,
        batch_size=batch_size,
        max_processes=1)

    # 4. Create an AdaptiveModel
    # a) which consists of an embedding model as a basis.
    # Word embedding models only converts words it has seen during training to embedding vectors.
    language_model = LanguageModel.load(lang_model)
    # b) and a prediction head on top that is suited for our task => Text classification
    prediction_head = TextClassificationHead(
        layer_dims=[300,600,len(label_list)],
        class_weights=data_silo.calculate_class_weights(task_name="text_classification"),
        num_labels=len(label_list))

    model = AdaptiveModel(
        language_model=language_model,
        prediction_heads=[prediction_head],
        embeds_dropout_prob=0.1,
        lm_output_types=["per_sequence"],
        device=device)

    # 5. Create an optimizer
    model, optimizer, lr_schedule = initialize_optimizer(
        model=model,
        learning_rate=3e-5,
        device=device,
        n_batches=len(data_silo.loaders["train"]),
        n_epochs=n_epochs)

    # 6. Feed everything to the Trainer, which keeps care of growing our model into powerful plant and evaluates it from time to time
    trainer = Trainer(
        model=model,
        optimizer=optimizer,
        data_silo=data_silo,
        epochs=n_epochs,
        n_gpu=n_gpu,
        lr_schedule=lr_schedule,
        evaluate_every=evaluate_every,
        device=device)

    # 7. Let it grow
    trainer.train()


if __name__ == "__main__":
    doc_classifcation()

# fmt: on
