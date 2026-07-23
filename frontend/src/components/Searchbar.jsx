export default function Searchbar({ 
    address, setStartAddress,
    onSearch, isLoading, 
    status 
}) {
    <div id="searchbar">
        <div className="field">
            <label htmlFor="address">Address</label>
            <input
                id="address"
                type="text"
                placeholder="e.g. Columbus, OH"
                value={address}
                onChange={(e) => setStartAddress(e.target.value)}
            />
        </div>
    </div>
}
