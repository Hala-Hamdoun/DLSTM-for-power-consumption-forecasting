from numpy.random import seed
from pandas import DataFrame
from pandas import Series
from pandas import concat
from pandas import read_csv
from pandas import datetime
from sklearn.metrics import mean_squared_error
from sklearn.preprocessing import MinMaxScaler
from keras.models import Sequential
from keras.layers import Dense,Dropout
from keras.layers import LSTM
from keras.optimizers import adam
from math import sqrt
from matplotlib import pyplot
import matplotlib.pyplot as plt
import numpy
import sys 
from numpy import concatenate
import tensorflow as tf
import random as rn
import os
os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"   # see issue #152
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ['PYTHONHASHSEED'] = '0'
numpy.random.seed(42)
rn.seed(12345)
session_conf = tf.ConfigProto(intra_op_parallelism_threads=1, inter_op_parallelism_threads=1)

from keras import backend as K
tf.set_random_seed(1234)

sess = tf.Session(graph=tf.get_default_graph(), config=session_conf)
K.set_session(sess)
# compute RMSPE
def RMSPE(x,y):
	result=0
	for i in range(len(x)):
		result += ((x[i]-y[i])/x[i])**2
	result /= len(x)
	result = sqrt(result)
	result *= 100
	return result

# compute MAPE
def MAPE(x,y):
	result=0
	for i in range(len(x)):
		result += abs((x[i]-y[i])/x[i])
	result /= len(x)
	result *= 100
	return result

# date-time parsing function for loading the dataset
def parser(x):
	return datetime.strptime(x,'%m/%d/%Y')

# frame a sequence as a supervised learning problem
def timeseries_to_supervised(data, lag=1):
	df = DataFrame(data)
	columns = [df.shift(i) for i in range(1, lag+1)]
	columns.append(df)
	df = concat(columns, axis=1)
	df.fillna(0, inplace=True)
	print (df)
	return df

# create a differenced series
def difference(dataset, interval=1):
	diff = list()
	for i in range(interval, len(dataset)):
		value = dataset[i] - dataset[i - interval]
		diff.append(value)
	return Series(diff)

# invert differenced value
def inverse_difference(history, yhat, interval=1):
	return yhat + history[-interval]

# scale train and test data to [-1, 1]
def scale(train, test):
	# fit scaler
	scaler = MinMaxScaler(feature_range=(-1, 1))
	scaler = scaler.fit(train)
	# transform train
	train = train.reshape(train.shape[0], train.shape[1])
	train_scaled = scaler.transform(train)
	# transform test
	test = test.reshape(test.shape[0], test.shape[1])
	test_scaled = scaler.transform(test)
	return scaler, train_scaled, test_scaled

# inverse scaling for a forecasted value
def invert_scale(scaler, X, value):
	new_row = [x for x in X] + [value]
	array = numpy.array(new_row)
	array = array.reshape(1, len(array))
	inverted = scaler.inverse_transform(array)
	return inverted[0, -1]

# fit an LSTM network to training data
def fit_lstm(train, batch_size, nb_epoch, neurons):
	X, y = train[:, 0:-1], train[:, -1]
	X = X.reshape(X.shape[0], 1, X.shape[1])
	model = Sequential()
	model.add(LSTM(neurons[0], batch_input_shape=(batch_size, X.shape[1], X.shape[2]), stateful=True, return_sequences=True))
	model.add(LSTM(neurons[1], batch_input_shape=(batch_size, X.shape[1], X.shape[2]), stateful=True, return_sequences=True))
	model.add(LSTM(neurons[2], batch_input_shape=(batch_size, X.shape[1], X.shape[2]), stateful=True, return_sequences=True))
	model.add(LSTM(neurons[3], batch_input_shape=(batch_size, X.shape[1], X.shape[2]), stateful=True, return_sequences=True))
	model.add(LSTM(neurons[4], batch_input_shape=(batch_size, X.shape[1], X.shape[2]),stateful=True))
	#model.add(Dropout(0.3))
	model.add(Dense(1))
	model.compile(loss='mean_squared_error', optimizer='adam')
	for i in range(nb_epoch):
		print('epoch:',i+1)
		model.fit(X, y, epochs=1, batch_size=batch_size, verbose=0)
		model.reset_states()
	return model

# make a one-step forecast
def forecast_lstm(model, batch_size, X):
	X = X.reshape(1, 1, len(X))
	yhat = model.predict(X, batch_size=batch_size)
	return yhat[0,0]

# load dataset
series = read_csv('monore.csv', header=0, parse_dates=[0], index_col=0, squeeze=True, date_parser=parser)

# transform data to be stationary
raw_values = series.values
diff_values = difference(raw_values, 1)

# transform data to be supervised learning
supervised = timeseries_to_supervised(diff_values, 1)
supervised_values = supervised.values

# split data into train and test-sets
#size = int(len(supervised_values) * 0.7) #two months as train and the third month as test
#train, test = supervised_values[0:size], supervised_values[size:len(supervised_values)]
size = int(len(supervised_values) * 0.67)
test_size = len(supervised_values) - size
train, test = supervised_values[0:size,:], supervised_values[size:len(supervised_values),:]

# transform the scale of the data
scaler, train_scaled, test_scaled = scale(train, test)

# fit the model
neurons= [30,20,10,5,1]
lstm_model = fit_lstm(train_scaled, 1, 2368, neurons)
# forecast the entire training dataset to build up state for forecasting
train_reshaped = train_scaled[:, 0].reshape(len(train_scaled), 1, 1)
lstm_model.predict(train_reshaped, batch_size=1)

# walk-forward validation on the test data
predictions = list()
for i in range(len(test_scaled)):
	# make one-step forecast
	X, y = test_scaled[i, 0:-1], test_scaled[i, -1]
	yhat = forecast_lstm(lstm_model, 1, X)
	# invert scaling
	yhat = invert_scale(scaler, X, yhat)
	# invert differencing
	yhat = inverse_difference(raw_values, yhat, len(test_scaled)+1-i)
	# store forecast
	predictions.append(yhat)
	expected = raw_values[len(train) + i + 1]
	print('Date=%d, Predicted=%f, Expected=%f' % (i+1, yhat, expected))

# report performance
rmse = sqrt(mean_squared_error(raw_values[size:len(supervised_values)], predictions))
print('Test RMSE: %.3f' % rmse)
MAPE_test = MAPE(raw_values[size:len(supervised_values)], predictions)
print('Test MAPE: %.5f' % MAPE_test)
rmspe_test = RMSPE(raw_values[size:len(supervised_values)],predictions)
print('Test RMSPE: %.4f' % rmspe_test)
sys.stdout=open("testresult30.txt","w")
print('deep30,20,10,5,1' )
print('Test RMSE: %.3f' % rmse )
print('Test MAPE: %.5f' % MAPE_test)
print('Test RMSPE: %.4f' % rmspe_test)
# line plot of observed vs predicted
pyplot.plot(raw_values[size:len(supervised_values)])
pyplot.plot(predictions)
pyplot.show()
