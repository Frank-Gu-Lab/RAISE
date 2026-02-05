#Interface for connecting to a remote Database
#from dotenv import load_dotenv, find_dotenv

from pymongo import MongoClient
from pymongo.database import Database
from pymongo.collection import Collection
import gridfs


from utils.secret_credentials import MONGODB_CONNECTION_STRING, MONGODB_PASSWORD
from typing import List, Any, Dict
from datetime import datetime

import numpy as np


class DBInterface:
    def __init__(self, db_name: str, collection_name: str) -> None:
        #load_dotenv(find_dotenv())
        parse1, parse2 = MONGODB_CONNECTION_STRING.split('<password>')
        self.connection_string = parse1 + MONGODB_PASSWORD + parse2
        
        self.client: MongoClient = MongoClient(self.connection_string)

        self.database: Database = self.client[db_name]
        self.collection: Collection = self.database[collection_name]
    
    def get_database_names(self) -> List[str]:
        return self.client.list_database_names()

    def get_collection_names(self, db: Database | None = None) -> List[str]:
        if db is not None:
            return db.list_collection_names()
        return self.database.list_collection_names()
    
    def get_database(self, db_name: str) -> Database:
        if db_name not in self.get_database_names():
            raise ValueError('No Database with this name.')
        return self.client[db_name]
    
    def set_current_database(self, db: Database) -> None:
        self.database = db
    
    def set_current_collection(self, collection: Collection) -> None:
        self.collection = collection
    
    def write_metadata_to_db(self,
                             slot_num: int, 
                             well_name: str, 
                             timepoint: str, 
                             img_height: int, 
                             img_width: int,
                             fname: str,
                             formulation: Dict[str, float],
                             datetime: datetime):
        #img_id = self.write_image_to_db(db, img)
        metadata = {'slot_number': slot_num, 
                    'well_name': well_name, 
                    'time_point': timepoint, 
                    'img_height': img_height, 
                    'img_width': img_width, 
                    'file_name': fname, 
                    'formulation': formulation,
                    'time': datetime, 
                    }
        #collection = db[collection_name]
        return self.collection.insert_one(metadata).inserted_id
    
    def read_metadata_from_db(self):
        pass
    
    def write_image_metadata_to_db(self, db: Database | None = None, collection: Collection | None = None, **kwargs) -> None:
        assert 'DATE' in kwargs
        assert 'DECK_LOCATION' in kwargs
        assert 'DATA_FILEPATH' in kwargs
        post = collection.insert_one(kwargs)
        return post.inserted_id
    
    def write_image_to_db(self, db: Database, img: np.ndarray) -> None:
        fs: gridfs.GridFS = gridfs.GridFS(db)
        img_shape = img.shape
        img_bytes = img.tobytes()
        return fs.put(img_bytes, shape=img_shape, dtype=str(img.dtype))

    def read_image_from_db(self, db: Database, img_id: Any) -> np.ndarray:
        fs: gridfs.GridFS = gridfs.GridFS(db)
        obj = fs.get(img_id)
        img_bytes = obj.read()
        img_shape = obj.shape
        img_1d  = np.frombuffer(img_bytes, obj.dtype)
        return np.reshape(img_1d, img_shape)
    


        
if __name__ == '__main__':
    database_interface: DBInterface = DBInterface('SDL5', 'TESTS')
    database_interface.write_metadata_to_db(slot_num=1, 
                                            well_name='A1', 
                                            timepoint='0_mins', 
                                            img_height=480, 
                                            img_width=720, 
                                            fname='./TEST.jpg', 
                                            formulation={'H20': 294, 'SDS': 6}, 
                                            datetime=datetime.now())
