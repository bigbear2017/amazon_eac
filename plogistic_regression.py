from numpy import array, hstack
from sklearn import metrics, cross_validation, linear_model
import sklearn.ensemble #.RandomForestClassifier
from scipy import sparse
from itertools import combinations

import numpy as np
import pandas as pd

def group_data(data, degree=4, hash=hash):
    """ 
    numpy.array -> numpy.array
    
    Groups all columns of data into all combinations of triples
    """
    new_data = []
    m,n = data.shape
    for indicies in combinations(range(n), degree):
        new_data.append([hash(tuple(v)) for v in data[:,indicies]])
    return array(new_data).T

def OneHotEncoder(data, keymap=None):
     """
     OneHotEncoder takes data matrix with categorical columns and
     converts it to a sparse binary matrix.
     
     Returns sparse binary matrix and keymap mapping categories to indicies.
     If a keymap is supplied on input it will be used instead of creating one
     and any categories appearing in the data that are not in the keymap are
     ignored
     """
     if keymap is None:
          keymap = []
          for col in data.T:
               uniques = set(list(col))
               keymap.append(dict((key, i) for i, key in enumerate(uniques)))
     total_pts = data.shape[0]
     outdat = []
     for i, col in enumerate(data.T):
          km = keymap[i]
          num_labels = len(km)
          spmat = sparse.lil_matrix((total_pts, num_labels))
          for j, val in enumerate(col):
               if val in km:
                    spmat[j, km[val]] = 1
          outdat.append(spmat)
     outdat = sparse.hstack(outdat).tocsr()
     return outdat, keymap

def create_test_submission(filename, prediction):
    content = ['id,ACTION']
    for i, p in enumerate(prediction):
        content.append('%i,%f' %(i+1,p))
    f = open(filename, 'w')
    f.write('\n'.join(content))
    f.close()
    print 'Saved'

def cv_loop(X, y, model, N, N_JOBS = 4, SEED=25):
    scores = cross_validation.cross_val_score(model, X, y,
            scoring='roc_auc', #score_func = metrics.auc_score,
            pre_dispatch = N_JOBS,
            n_jobs = N_JOBS,
            cv = cross_validation.StratifiedShuffleSplit(y, random_state=SEED, n_iter=N))
    return sum(scores) / N
    
def main(train='train.csv', test='test.csv', submit='logistic_pred.csv', SEED=25):    
    print "Reading dataset..."
    train_data = pd.read_csv(train)
    test_data = pd.read_csv(test)
    all_data = np.vstack((train_data.ix[:,1:-1], test_data.ix[:,1:-1]))

    num_train = np.shape(train_data)[0]
    
    # Transform data
    print "Transforming data..."
    dp = group_data(all_data, degree=2) 
    dt = group_data(all_data, degree=3)
    #dc = group_data(all_data, degree=4)
    #d5 = group_data(all_data, degree=5)

    y = array(train_data.ACTION)
    X = all_data[:num_train]
    X_2 = dp[:num_train]
    X_3 = dt[:num_train]
    #X_4 = dc[:num_train]
    #X_5 = d5[:num_train]

    X_test = all_data[num_train:]
    X_test_2 = dp[num_train:]
    X_test_3 = dt[num_train:]
    #X_test_4 = dc[num_train:]
    #X_test_5 = d5[num_train:]

    X_train_all = np.hstack((X, X_2, X_3)) #, X_4))#, X_5))
    X_test_all = np.hstack((X_test, X_test_2, X_test_3)) #, X_test_4))#, X_test_5))
    num_features = X_train_all.shape[1]
   
    #model = sklearn.ensemble.RandomForestClassifier(n_estimators=100) 
    model = linear_model.LogisticRegression()
    model.predict = lambda M, x: M.predict_proba(x)[:,1]
    
    # Xts holds one hot encodings for each individual feature in memory
    # speeding up feature selection 
    Xts = [OneHotEncoder(X_train_all[:,[i]])[0] for i in range(num_features)]
    
    print "Performing greedy feature selection..."
    score_hist = []
    N = 15
    good_features = set([])
    # Greedy feature selection loop
    while len(score_hist) < 2 or score_hist[-1][0] > score_hist[-2][0]:
        scores = []
        for f in range(len(Xts)):
            if f not in good_features:
                feats = list(good_features) + [f]
                Xt = sparse.hstack([Xts[j] for j in feats]).tocsr()
                score = cv_loop(Xt, y, model, N, SEED=SEED)
                scores.append((score, f))
                #print "Feature: %i Mean AUC: %f" % (f, score)
                print ("%f " % score),
        print
        good_features.add(sorted(scores)[-1][1])
        score_hist.append(sorted(scores)[-1])
        print "Current features: %s" % sorted(list(good_features))
    
    # Remove last added feature from good_features
    good_features.remove(score_hist[-1][1])
    good_features = sorted(list(good_features))
    print "Selected features %s" % good_features
    
    print "Performing hyperparameter selection..."
    # Hyperparameter selection loop
    score_hist = []
    Xt = sparse.hstack([Xts[j] for j in good_features]).tocsr()

    for C in np.logspace(1, 4, 20, base=2):
        model.C = C
        score = cv_loop(Xt, y, model, N)
        score_hist.append((score,C))
        print "C: %f Mean AUC: %f" %(C, score)
    bestScore, bestC = sorted(score_hist)[-1]
    print "Best C value: %f" % (bestC)

    with open('scores.txt', 'a') as f:
        f.write('%s: C=%f AUC=%f %s\n' % (submit, bestC, bestScore, repr(good_features)))

    print "Performing One Hot Encoding on entire dataset..."
    Xt = np.vstack((X_train_all[:,good_features], X_test_all[:,good_features]))
    Xt, keymap = OneHotEncoder(Xt)
    X_train = Xt[:num_train]
    X_test = Xt[num_train:]
    
    print "Training full model..."
    model.fit(X_train, y)
    
    print "Making prediction and saving results..."
    preds = model.predict_proba(X_test)[:,1]
    create_test_submission(submit, preds)
    
if __name__ == "__main__":
    args = { 'train':  'data/train.csv',
             'test':   'data/test.csv',
             'submit': 'logistic_regression_pred.csv' }
    #main(**args)
    for seed in range(1,21):
        main(train='data/train.csv', test='data/test.csv', submit='logistic_regression_pred_%d.csv' % seed, SEED=seed)