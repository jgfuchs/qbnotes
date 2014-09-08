import os, hashlib
import json
from datetime import date
from functools import wraps

from flask import Flask, request, session, g, redirect, url_for, abort, render_template, flash, Response
from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.markdown import Markdown

# general app initialization and configuration

heroku = os.environ.get('HEROKU') == '1'

if heroku:
	db_uri = os.environ['DATABASE_URL']
else:
	db_uri = 'sqlite:///db.sqlite3'

app = Flask(__name__)
app.config.update(dict(
	SQLALCHEMY_DATABASE_URI=db_uri,
    SECRET_KEY='43316b82bca7c9847536d08abaae40a0',
    
    PASSWORD_HASH='11de2afa581597d4846ccf4cc6de36e7bc9789a3e044e29baca35f7f',
    
    version='0.3.2'
))

Markdown(app)
db = SQLAlchemy(app)

class Group(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	name = db.Column(db.String)

	def __init__(self, name):
		self.name = name

	def __repr__(self):
		return '<Group %s>' % (self.name)

class Entry(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	title = db.Column(db.String)
	creator = db.Column(db.String)
	notes = db.Column(db.String)

	date_added = db.Column(db.Date)

	group_id = db.Column(db.Integer, db.ForeignKey('group.id'))
	group = db.relationship('Group', backref=db.backref('entries', lazy='dynamic'))

	def __init__(self, title, creator, notes, group):
		self.title = title
		self.creator = creator
		self.notes = notes
		self.group = group
		self.date_added = date.today()

	def __repr__(self):
		return '<Entry \'%s\'>' % self.title

def login_required(f):
	@wraps(f)
	def decorated_function(*args, **kwargs):
		if not session.get('logged_in'):
			return redirect(url_for('login'))
		return f(*args, **kwargs)
	return decorated_function

# main app pages

@app.route('/')
@login_required
def all_groups():
	groups = Group.query.all()
	return render_template('all_groups.html', groups=groups)

@app.route('/group/<int:group_id>')
@login_required
def group_detail(group_id):
	group = Group.query.get_or_404(group_id)
	return render_template('group_detail.html', group=group)

@app.route('/entry/<int:entry_id>')
@login_required
def entry_detail(entry_id):
	entry = Entry.query.get_or_404(entry_id)
	return render_template('entry_detail.html', entry=entry)

@app.route('/group/new', methods=['POST'])
def new_group():
	if not session.get('logged_in'):
		abort(401)

	if not request.form['name']:
		abort(400)

	g = Group(request.form['name'])
	db.session.add(g)
	db.session.commit()

	return redirect(url_for('all_groups'))

@app.route('/group/<int:group_id>/new', methods=['GET', 'POST'])
@login_required
def new_entry(group_id):
	g = Group.query.get_or_404(group_id)
	
	if request.method == 'POST':
		if not (request.form['title'] and request.form['creator'] and request.form['notes']):
			abort(400)

		e = Entry(request.form['title'], request.form['creator'], request.form['notes'], g)

		db.session.add(e)
		db.session.commit()
	
		return redirect(url_for('entry_detail', entry_id=e.id))
	
	return render_template('new_entry.html', group=g)

@app.route('/entry/<int:entry_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_entry(entry_id):
	e = Entry.query.get_or_404(entry_id)
		
	if request.method == 'POST':
		if not (request.form['title'] and request.form['creator'] and request.form['notes']):
			abort(400)

		e.title = request.form['title']
		e.creator = request.form['creator']
		e.notes = request.form['notes']
		
		db.session.commit()
	
		return redirect(url_for('entry_detail', entry_id=e.id))
	
	return render_template('edit_entry.html', entry=e)

@app.route('/login', methods=['GET', 'POST'])
def login():
	error = None
	if request.method == 'POST':
		if hashlib.sha224(request.form['password']).hexdigest() == app.config['PASSWORD_HASH']:
			session['logged_in'] = True
			return redirect(url_for('all_groups'))
		else:
			error = 'Wrong password!'
			
	return render_template('login.html', error=error)

@app.route('/logout')
def logout():
	session['logged_in'] = False
	return redirect(url_for('login'))
	
@app.route('/download')
@login_required
def download():
	obj = {}
	for g in Group.query.all():
		obj[g.name] = {}
		for e in g.entries.all():
			obj[g.name][e.title] = {
				'creator': e.creator,
				'notes': e.notes,
				'date': str(e.date_added)}
		
	return Response(json.dumps(obj, indent=4, separators=(',', ': ')), mimetype='text/json')

if __name__ == '__main__':
	app.run(host='0.0.0.0', debug=True)

