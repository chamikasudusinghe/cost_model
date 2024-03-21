import os
import io
import logging
import gc
import hydra

from hydra.core.config_store import ConfigStore
from utils.data_utils import *
from utils.modeling import *
from utils.train_utils import *

@hydra.main(config_path="conf", config_name="config")
def main(conf):
    # Defining logger
    log_filename = [part for part in conf.training.log_file.split('/') if len(part) > 3][-1]
    log_folder_path = os.path.join(conf.experiment.base_path, "logs/")
    if not os.path.exists(log_folder_path):
        os.makedirs(log_folder_path)
    log_file = os.path.join(log_folder_path, log_filename)
    logging.basicConfig(filename = log_file,
                        filemode='a',
                        level = logging.DEBUG,
                        format = '%(asctime)s:%(levelname)s:  %(message)s')
    logging.info(f"Starting experiment {conf.experiment.name}")
    train_device = torch.device(conf.training.training_gpu)
    
    # Defining the model
    logging.info("Defining the model")
    model = Model_Recursive_LSTM_v2(
        input_size=conf.model.input_size,
        comp_embed_layer_sizes=list(conf.model.comp_embed_layer_sizes),
        drops=list(conf.model.drops),
        loops_tensor_size=8,
        train_device=conf.training.training_gpu,
    )
    
    # Load model weights and continue training if specified  
    if conf.training.continue_training:
        print(f"Continue training using model from {conf.training.model_weights_path}")
        model.load_state_dict(torch.load(conf.training.model_weights_path, map_location=train_device))
    
    # Enable gradient tracking for training
    for param in model.parameters():
        param.requires_grad = True
        
    # Reading data
    logging.info("Reading the dataset")
    train_bl_1 = []
    train_bl_2 = []
    val_bl = []
    
    # Training
    train_file_path = os.path.join( conf.experiment.base_path, "batched/train/", f"{Path(conf.data_generation.train_dataset_file).parts[-1][:-4]}_CPU.pt")
    if os.path.exists(train_file_path):
        print(f"Loading second part of the training set {train_file_path} into the CPU")
        with open(train_file_path, "rb") as file:
            train_bl_2 = torch.load(train_file_path, map_location="cpu")
            
    train_file_path = os.path.join(conf.experiment.base_path, "batched/train/", f"{Path(conf.data_generation.train_dataset_file).parts[-1][:-4]}_GPU.pt")
    
    print(f"Loading first part of the training set {train_file_path} into device: {train_device}")
    with open(train_file_path, "rb") as file:
        train_bl_1 = torch.load(train_file_path, map_location=train_device)
    
    # Fuse loaded training batches
    train_bl = train_bl_1 + train_bl_2 if len(train_bl_2) > 0 else train_bl_1
    
    # Validation
    validation_file_path = os.path.join( conf.experiment.base_path, "batched/valid/", f"{Path(conf.data_generation.valid_dataset_file).parts[-1][:-4]}.pt")
    print(f"Loading Validation set {validation_file_path} into the CPU")
    with open(validation_file_path, "rb") as file:
        val_bl = torch.load(validation_file_path, map_location='cpu')
    
    
    # Defining training params
    criterion = mape_criterion
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=conf.training.lr, weight_decay=0.15e-1
    )
    logger = logging.getLogger()
    if conf.wandb.use_wandb:
        # Intializing wandb
        wandb.init(project=conf.wandb.project)
        wandb.config = dict(conf)
        wandb.watch(model)
    
    # Training
    print("Training the model")
    bl_dict = {"train": train_bl, "val": val_bl}
    train_model(
        config=conf,
        model=model,
        criterion=criterion,
        optimizer=optimizer,
        max_lr=conf.training.lr,
        dataloader=bl_dict,
        num_epochs=conf.training.max_epochs,
        logger=logger,
        log_every=1,
        train_device=conf.training.training_gpu,
    )


if __name__ == "__main__":
    main()
