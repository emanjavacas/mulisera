import os 
import re
import pickle
from collections import Counter
import numpy as np  
import nltk
from torch.utils.data import DataLoader, Dataset
from vocab import Vocabulary

COCO_PATH = '/roaming/u1257964/coco_mulisera'
M30K_PATH = '/roaming/u1257964/multi30k-dataset/'

def build_vocabulary(captions, path='.', threshold=4):
    """
    Build a simple vocabulary wrapper.
    """
    print("Building vocabulary")
    counter = Counter()
    for i, caption in enumerate(captions):
        counter.update(caption)

    # Discard if the occurrence of the word is less than min_word_cnt.
    words = [word for word, cnt in counter.items() if cnt >= threshold]

    # Create a vocab wrapper and add some special tokens.
    vocab = Vocabulary()
    vocab.add_word('<pad>')
    vocab.add_word('<start>')
    vocab.add_word('<end>')
    vocab.add_word('<unk>')
    # Add words to the vocabulary.
    for i, word in enumerate(words):
        vocab.add_word(word)
    print('Num words:', vocab.idx)
    path = os.path.join(path, 'vocab.pkl')
    with open(path, 'w') as f:
        pickle.dump(vocab, f,
                    pickle.HIGHEST_PROTOCOL)
    return vocab


def collate_fn(data):
    """Build mini-batch tensors from a list of (image, caption) tuples.
    Args:
        data: list of (image, caption) tuple.
            - image: torch tensor of shape (3, 256, 256).
            - caption: torch tensor of shape (?); variable length.

    Returns:
        images: torch tensor of shape (batch_size, 3, 256, 256).
        targets: torch tensor of shape (batch_size, padded_length).
        lengths: list; valid length for each padded caption.
    """
    # Sort a data list by caption length
    data.sort(key=lambda x: len(x[1]), reverse=True)
    images, captions, ids, img_ids = zip(*data)

    # Merge images (convert tuple of 3D tensor to 4D tensor)
    images = torch.stack(images, 0)

    # Merget captions (convert tuple of 1D tensor to 2D tensor)
    lengths = [len(cap) for cap in captions]
    targets = torch.zeros(len(captions), max(lengths)).long()
    for i, cap in enumerate(captions):
        end = lengths[i]
        targets[i, :end] = cap[:end]

    return images, targets, lengths, ids


# prefix = lambda x: " ".join(map(lambda y: l+"_"+y, x.split()))
def tokenize(s):
    """
    Remove non-alphanumeric characters, then tokenize.
    
    s : str
        String to tokenize.
    """
    s = re.sub(r'([^\s\w]|_)+', '', s)
    tokens = nltk.tokenize.word_tokenize(s.lower().decode('utf-8'))
    return tokens

def read_m30K(data_path, lang, split, lang_prefix=False):
    """
    Reads data from Multi30K task 2 comparable.
    
    data_path : str
        Root of the Multi30K data folder.
    split : str
        train, val or test.
    lang_prefix : bool
        Place en_ or de_ prefix infront of each token.
    """
    if split == 'test':
        split = 'test_2016'
    img_path = data_path + '/data/imgfeats/'
    imgpath = os.path.join(img_path, split +'-resnet50-avgpool.npy')
    image_vectors = np.load(imgpath).astype("float32")
    images = []
    caps = []
    img_ids = []
    for i in range(1, 6):
        text = '{}.lc.norm.tok.{}.{}'.format(split, i, lang)
        path = os.path.join('/data/task2/tok/', text)
        # Add language prefix to each word in all captions like 'en_woman en_sits en_on en_the en_bench.'
        with open(data_path + path) as f:
            t = f.read().split('\n')
            #TODO implement lang prefix
            if lang_prefix:
                pass
            caps.append(t[:-1])
    captions = [y for x in caps for y in x]
    images = np.repeat(image_vectors, 5, axis=0)
    return images, captions   


def read_coco(data_path, split, lang_prefix=False, downsample=False):
    """
    Reads data from Multi30K task 2 comparable.
    
    data_path : str
        Root of the coco_mulisra directory created with coco_process.py
    split : str
        train, val or test.
    lang_prefix : bool
        Place en_ prefix infront of each token.
    downsample : int
        Number of images to keep.
    """
    img_path = os.path.join(data_path, 'imgfeats')
    img_path = os.path.join(img_path, split +'-resnet50-avgpool.npy')
    image_vectors = np.load(img_path).astype("float32")
    caps = []
    text = '{}_captions.txt'.format(split)
    path = os.path.join(data_path, text)
    with open(path) as f:
        t = f.read().split('\n')
        #TODO implement lang_prefix
        if lang_prefix:
            pass
        caps.append(t[:-1])
    captions = np.array([y.split('\t')[0] for x in caps for y in x])
    if downsample:
        #Get indices for a random subsample for the image vectors
        a = np.arange(image_vectors.shape[0] - 1)
        np.random.shuffle(a)
        img_inds = a[:downsample]
        print(img_inds)
        #Generate indices for the corresponding captions
        cap_inds = [np.arange(x*5, (x*5)+5) for x in img_inds]
        cap_inds = [y for x in cap_inds for y in x]
        print(cap_inds)
        #Pick the samples
        image_vectors = image_vectors[img_inds]
        captions = captions[cap_inds]
    #Repeast each image 5 times
    images = np.repeat(image_vectors, 5, axis=0)
    return images, captions


def load_data(name, split, lang_prefix, downsample=False):
    print("Loading {}, split {}".format(name, split))
    if name == 'coconumpy':
        # Downsample coco valset because its huge
        if split == 'val':
            downsample = 5000
        path = COCO_PATH
        img, cap = read_coco(path, split, lang_prefix, downsample)
    elif name == 'm30ken':
        path = M30K_PATH
        img, cap = read_m30K(path, 'en', split, lang_prefix)
    elif name == 'm30kde':
        path = M30K_PATH
        img, cap = read_m30K(path, 'de', split, lang_prefix)
    else:
        raise NotImplementedError
    print("N images {}, N captions {}".format(len(img), len(cap)))
    return img, cap
        
        

class ImageCaptionDataset(Dataset):
    """
    Load precomputed captions and image features
    """

    def __init__(self, captions, images, vocab=None):
        # Captions
        self.captions = captions
        self.images = images
        self.length = len(self.captions)
        print("Tokenizing")
        self.tokenized_captions = [tokenize(x) for x in captions]
        if not vocab:
            self.vocab = build_vocabulary(self.tokenized_captions)

    def __getitem__(self, index):
        image = torch.Tensor(self.images[index])
        tokens = self.tokenized_captions[index]
        caption = []
        caption.append(vocab('<start>'))
        caption.extend([vocab(token) for token in tokens])
        caption.append(vocab('<end>'))
        target = torch.Tensor(caption)
        return image, target, index, index

    def __len__(self):
        return self.length

class DatasetCollection():
    
    def __init__(self):
        self.data_loaders = {}
        self.data_sets = {}
        self.val_loaders = {}

    def add_trainset(self, name, dset, batch_size):
        data_loader = DataLoader(dataset=dset,
                                 batch_size=batch_size,
                                 shuffle=True,
                                 pin_memory=True,
                                 collate_fn=collate_fn)
        self.data_sets[name] = dset
        self.data_loaders[name] = iter(data_loader)
    
    def add_valset(self, name, dset, batch_size):
        data_loader = DataLoader(dataset=dset,
                                 batch_size=batch_size,
                                 shuffle=False,
                                 pin_memory=True,
                                 collate_fn=collate_fn)
        self.val_loaders[name] = data_loader
    
    def compute_joint_vocab(self):
        """Join the captions of all data sets and recompute the vocabulary."""
        caps = [v.tokenized_captions for k, v in self.data_sets.items()]
        caps = [y for x in caps for y in x]
        vocab = build_vocabulary(caps)
        for i in self.data_sets:
            self.data_sets[i].vocab = vocab

    def __iter__(self):
        return self

    def next(self):
        """Pick a data loader, either yield next batch or if ran out re-init and yield."""
        k = random.choice(self.data_loaders.keys())
        loader = self.data_sets[k]
        try:
            image, target, index, index = next(loader)
        except StopIteration:
            self.data_loaders[k] = iter(self.data_loaders[k])
            loader = self.data_loaders[k]
            image, target, index, index = next(loader)
        return image, target, index, index 


def get_loaders(data_sets, lang_prefix, downsample, batch_size):
    data_loaders = DatasetCollection()
    for name in data_sets:
        train_img, train_cap = load_data(name, 'train', lang_prefix, downsample)
        val_img, val_cap = load_data(name, 'val', lang_prefix, downsample)
        trainset = ImageCaptionDataset(train_cap, train_img)
        valset = ImageCaptionDataset(val_cap, val_img, vocab=trainset.vocab)
        data_loaders.add_trainset(name, trainset, batch_size)
        data_loaders.add_valset(name, valset, batch_size)
    data_loaders.compute_joint_vocab()
    return data_loaders 
