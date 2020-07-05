import os
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import  DataLoader
from tqdm import tqdm, trange
from transformers import AutoConfig
from modeling import BertForSentimentClassification, AlbertForSentimentClassification
from dataset import SSTDataset
from arguments import args


def get_accuracy_from_logits(logits, labels):
	#Get probabilities that the sentiments is positive by passing the logits through a sigmoid
	probs = torch.sigmoid(logits.unsqueeze(-1))
	#Convert probabilities to predictions, 1 being positive and 0 being negative
	preds = (probs > 0.5).long()
	#Check which predictions are the same as the ground truth and calculate the accuracy
	acc = (preds.squeeze() == labels).float().mean()

	return acc

def evaluate(model, criterion, dataloader):

	model.eval()

	mean_acc, mean_loss, count = 0, 0, 0
	#We won't track the gradients since we're evaluating the model, not training it
	with torch.no_grad():
		#Get the sequence, attention masks, and labels from the dataloader
		for seq, attn_masks, labels in tqdm(dataloader, desc="Evaluating"):
			#Put the sequence, attention masks, and labels to the GPU, if available
			seq, attn_masks, labels = seq.to(device), attn_masks.to(device), labels.to(device)
			#Get the logits from the model
			logits = model(seq, attn_masks)
			#Calculate the mean loss using logits and labels
			mean_loss += criterion(logits.squeeze(-1), labels.float()).item()
			#Calculate the man accuracy using logits and labels
			mean_acc += get_accuracy_from_logits(logits, labels)

			count += 1
	#Return accuracy and loss
	return mean_acc / count, mean_loss / count

def train(model, criterion, optimizer, train_loader, val_loader, args):

	best_acc = 0
	for epoch in trange(args.num_eps, desc="Epoch"):
		model.train()
		for i, (seq, attn_masks, labels) in enumerate(tqdm(train_loader, desc="Training")):
			#Clear gradients
			optimizer.zero_grad()  
			#Convert these to cuda tensors a.k.a. put them to GPU (if available)
			seq, attn_masks, labels = seq.to(device), attn_masks.to(device), labels.to(device)
			#Obtain the logits from the model
			logits = model(seq, attn_masks)
			#Compute loss
			loss = criterion(logits.squeeze(-1), labels.float())
			#Backpropagate the gradients
			loss.backward()
			#Optimization step
			optimizer.step()
		#Calculate the validation accuracy and loss
		val_acc, val_loss = evaluate(model, criterion, val_loader)
		#Display the validation accuracy and loss
		print("Epoch {} complete! Validation Accuracy : {}, Validation Loss : {}".format(epoch, val_acc, val_loss))
		#If the validation accuracy of the current model is the best one yet
		if val_acc > best_acc:
			#Print the old best validation accuracy and the current one
			print("Best validation accuracy improved from {} to {}, saving model...".format(best_acc, val_acc))
			#Set the current validation accuracy as the best one
			best_acc = val_acc
			#Save the model
			model.save_pretrained(f'models/{args.model_name}/')

if __name__ == "__main__":

	#Create the model directory if it doesn't exist
	if not os.path.exists('models'):
		os.makedirs('models')
	#Configuration for the desired transformer model
	config = AutoConfig.from_pretrained(args.model_name)
	#Create the model with the desired transformer model
	if args.model_type == 'bert':
		model = BertForSentimentClassification.from_pretrained(args.model_name, config=config)
	elif args.model_type == 'albert':
		model = AlbertForSentimentClassification.from_pretrained(args.model_name, config=config)
	#CPU or GPU
	device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
	#Put the model to the GPU if available
	model = model.to(device)
	#Takes as the input the logits of the positive class and computes the binary cross-entropy 
	criterion = nn.BCEWithLogitsLoss()

	optimizer = optim.Adam(model.parameters(), lr = args.lr)
	
	train_set = SSTDataset(filename = 'data/train.tsv', maxlen = args.maxlen_train, model_name=args.model_name)
	val_set = SSTDataset(filename = 'data/dev.tsv', maxlen = args.maxlen_val, model_name=args.model_name)

	train_loader = DataLoader(train_set, batch_size = args.batch_size, num_workers = args.num_threads)
	val_loader = DataLoader(val_set, batch_size = args.batch_size, num_workers = args.num_threads)

	train(model, criterion, optimizer, train_loader, val_loader, args)
